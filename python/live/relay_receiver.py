"""A receiver for Reamer Research's relay: the process rr.Relay connects to.

rr.Relay (reamer_relay_* in C and C++) sends the orders a strategy returns
over a Unix domain socket and reads fills back. Something has to listen on
that socket and talk to the broker. Without Reamer Server, that something is
yours, and this file is a complete one in the standard library: the wire
codec, a socket server, and a paper broker that fills orders against the bars
you mark it with. Replace PaperBroker with calls to your broker's API to trade
for real; the codec and the server stay as they are.

    from relay_receiver import Receiver, PaperBroker

    broker = PaperBroker()
    with Receiver('/tmp/reamer-live.sock', broker):
        ...  # rr.Relay('/tmp/reamer-live.sock', ['AAPL']) from here on

Wire format (Reamer Research 4.11.1 and later, ABI 8):

  Every frame is   version u8 (1) | payload length u32 big-endian | payload
  and the payload's first byte is its type. Integers are big-endian, a double
  is its 8 IEEE-754 bytes in big-endian order, a string is a u16 big-endian
  byte length then that many UTF-8 bytes.

  Relay -> receiver
    0 NewOrder  strategy_id str, intent_id str, instrument str, side u8,
                order_type u8, quantity f64, limit_price f64, stop_price f64,
                position_effect u8, time_in_force u8, expire_time str,
                then, only when the order has a take profit, a stop loss or a
                one-cancels-other partner: ext_version u8 (1), take_profit
                f64, stop_loss f64, fields the relay sends as zero (see
                _EXT_REST), contingency_type u8 (1 one-cancels-other),
                linked_intent_id str, and more zero or empty fields.
    1 Cancel    strategy_id str, request_id str, target_order_id str
    2 Replace   strategy_id str, request_id str, target_order_id str,
                new_quantity f64, new_limit_price f64, new_stop_price f64,
                then, only when it moves a take profit or stop loss:
                ext_version u8 (1), new_take_profit f64, new_stop_loss f64,
                new_trailing_offset f64. A 0 there leaves that level as it is.

  Receiver -> relay
    1 OrderUpdate  intent_id str, instrument str, side u8, status u8,
                   filled_quantity f64, last_price f64, venue_order_id str,
                   commission f64, reason str, timestamp str

  side 0 buy, 1 sell. order_type 0 market, 1 limit, 2 stop.
  position_effect 0 open, 1 close. time_in_force 1 gtc, 2 ioc, 4 gtd.
  status 1 new, 2 partially filled, 3 filled, 4 cancelled, 5 rejected.

  intent_id is "<strategy_id>-<session nonce>-<n>", n counting from 1 as the
  backtest numbers orders. A cancel's target_order_id is one of those.
  filled_quantity is cumulative per intent_id: the relay moves its position by
  the increase. A take profit or stop loss fills under "<intent_id>:tp" or
  "<intent_id>:sl", against the entry. A position's exits placed by
  modify_position arrive as their own NewOrders, "<strategy_id>-<nonce>-p<k>:tp"
  or ":sl", position_effect close, linked one-cancels-other to each other.
  The relay reads intent_id, status, filled_quantity and last_price: an
  order ends when its status is filled, cancelled or rejected. It sends no
  acknowledgement of its own.

  The four on_bar actions arrive as these messages: modify_order as a Replace
  of the order (and a Cancel of "<intent_id>:tp" or ":sl" for a level it
  clears), modify_position as a Replace or Cancel of each exit it moves or
  clears and a NewOrder for each level it adds, close_all as one close
  NewOrder per position, cancel_all as one Cancel per resting order.
"""

import os
import socket
import struct
import threading

BUY, SELL = 0, 1
MARKET, LIMIT, STOP = 0, 1, 2
NEW, PARTIAL, FILLED, CANCELLED, REJECTED = 1, 2, 3, 4, 5

_MAX_PAYLOAD = 1 << 20
# After take_profit and stop_loss: stop_loss_limit, stop_loss_trailing_offset,
# trailing_offset (3 f64), offset_type u8, limit_offset f64, trigger_type u8,
# display_quantity, min_quantity (2 f64), exec_flags u32, contingency_type u8,
# linked_intent_id, account, destination (3 str), payload_schema u32,
# payload_len u32, payload bytes. The relay sends them as zero or empty, but
# for contingency_type and linked_intent_id on an exit modify_position places.


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError('truncated frame')
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return struct.unpack('>I', self.take(4))[0]

    def f64(self):
        return struct.unpack('>d', self.take(8))[0]

    def str(self):
        return self.take(struct.unpack('>H', self.take(2))[0]).decode('utf-8')

    def left(self):
        return len(self.data) - self.pos


def decode(payload):
    """One relay payload -> a dict with 'type' 'new_order', 'cancel' or 'replace'."""
    r = _Reader(payload)
    kind = r.u8()
    if kind == 1:
        return {'type': 'cancel', 'strategy_id': r.str(), 'request_id': r.str(),
                'target_order_id': r.str()}
    if kind == 2:
        o = {'type': 'replace', 'strategy_id': r.str(), 'request_id': r.str(),
             'target_order_id': r.str(), 'quantity': r.f64(), 'limit_price': r.f64(),
             'stop_price': r.f64(), 'take_profit': 0.0, 'stop_loss': 0.0}
        if r.left():
            if r.u8() != 1:
                raise ValueError('unknown replace extension version')
            o['take_profit'], o['stop_loss'] = r.f64(), r.f64()
            r.f64()
        if r.left():
            raise ValueError('bytes left after the replace')
        return o
    if kind != 0:
        raise ValueError(f'unknown message type {kind}')
    o = {'type': 'new_order', 'strategy_id': r.str(), 'intent_id': r.str(),
         'instrument': r.str(), 'side': r.u8(), 'order_type': r.u8(),
         'quantity': r.f64(), 'limit_price': r.f64(), 'stop_price': r.f64(),
         'is_close': r.u8() == 1, 'time_in_force': r.u8(), 'expire_time': r.str(),
         'take_profit': 0.0, 'stop_loss': 0.0, 'linked_intent_id': ''}
    if r.left():
        if r.u8() != 1:
            raise ValueError('unknown order extension version')
        o['take_profit'], o['stop_loss'] = r.f64(), r.f64()
        for _ in range(3):
            r.f64()
        r.u8(); r.f64(); r.u8(); r.f64(); r.f64(); r.u32()
        if r.u8() == 1:
            o['linked_intent_id'] = r.str()
        else:
            r.str()
        r.str(); r.str()
        r.u32()
        r.take(r.u32())
    if r.left():
        raise ValueError('bytes left after the order')
    return o


def _s(text):
    raw = text.encode('utf-8')
    return struct.pack('>H', len(raw)) + raw


def encode_update(intent_id, instrument, side, status, filled_qty, last_price,
                  venue_order_id='', commission=0.0, reason='', timestamp=''):
    """An OrderUpdate frame, ready to write to the relay's connection."""
    payload = (bytes([1]) + _s(intent_id) + _s(instrument) + bytes([side, status])
               + struct.pack('>dd', filled_qty, last_price) + _s(venue_order_id)
               + struct.pack('>d', commission) + _s(reason) + _s(timestamp))
    return bytes([1]) + struct.pack('>I', len(payload)) + payload


class Receiver:
    """Listens on socket_path and hands each decoded message to broker.

    broker needs on_order(order, report), on_cancel(cancel, report) and
    on_replace(replace, report), where report(intent_id, instrument, side,
    status, filled_qty, price) writes an OrderUpdate back to the connection
    that sent the order. Messages are
    handled on one background thread per connection, in the order sent.
    """

    def __init__(self, socket_path, broker):
        self.socket_path, self.broker = str(socket_path), broker
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self._server.listen(8)
        self._closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._closed:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        lock = threading.Lock()

        def report(intent_id, instrument, side, status, filled_qty, price, reason=''):
            frame = encode_update(intent_id, instrument, side, status, filled_qty, price,
                                  reason=reason)
            with lock:
                try:
                    conn.sendall(frame)
                except OSError:
                    pass   # the relay disconnected; its position is now stale

        def exact(n):
            buf = b''
            while len(buf) < n:
                chunk = conn.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError
                buf += chunk
            return buf

        with conn:
            try:
                while True:
                    head = exact(5)
                    length = struct.unpack('>I', head[1:])[0]
                    if head[0] != 1 or length > _MAX_PAYLOAD:
                        return   # malformed: close, as Reamer Server does
                    msg = decode(exact(length))
                    if msg['type'] == 'new_order':
                        self.broker.on_order(msg, report)
                    elif msg['type'] == 'replace':
                        self.broker.on_replace(msg, report)
                    else:
                        self.broker.on_cancel(msg, report)
            except (ConnectionError, OSError, ValueError):
                return

    def close(self):
        self._closed = True
        self._server.close()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def is_exit(intent_id):
    """True for a take profit or stop loss: "<id>:tp" or "<id>:sl"."""
    return intent_id.endswith((':tp', ':sl'))


class PaperBroker:
    """Fills orders against the bars you pass to mark(), with no broker at all.

    A market order fills at the next marked bar's open. A buy limit fills when
    the bar's low reaches it, a buy stop when the high does, at the limit or
    stop or the open if the bar opened through it; sells mirror that. Once an
    entry fills, its take profit and stop loss rest as one-cancels-other exits,
    checked from the next bar, the stop first when one bar reaches both; the
    exits modify_position places rest the same way, linked to each other. A
    close or an exit that fills takes the instrument's other exits with it.
    A Replace re-prices a resting order or exit, and moves a resting entry's
    take profit or stop loss. No fees, slippage or partial fills: this tests
    the plumbing, and the backtest's execution model (EXECUTION_SPEC.md) stays
    the one to trust for results.
    """

    def __init__(self):
        self._lock = threading.Condition()
        self._resting = []        # [order, report] waiting for a bar
        self.received = 0         # NewOrder, Cancel and Replace messages handled
        self.fills = []           # (intent_id, instrument, side, qty, price, ts)

    def _handled(self):
        self.received += 1
        self._lock.notify_all()

    def on_order(self, order, report):
        with self._lock:
            report(order['intent_id'], order['instrument'], order['side'], NEW, 0.0, 0.0)
            self._resting.append([order, report])
            self._handled()

    def on_cancel(self, cancel, report):
        with self._lock:
            target = cancel['target_order_id']
            for item in list(self._resting):
                o, rep = item
                if o['intent_id'] == target or o.get('parent') == target:
                    self._resting.remove(item)
                    rep(o['intent_id'], o['instrument'], o['side'], CANCELLED, 0.0, 0.0)
                elif is_exit(target) and o['intent_id'] == target[:-3]:
                    # An exit of an entry still resting: drop that level.
                    o['take_profit' if target.endswith(':tp') else 'stop_loss'] = 0.0
            self._handled()

    def on_replace(self, rep_msg, report):
        with self._lock:
            for o, rep in self._resting:
                if o['intent_id'] != rep_msg['target_order_id']:
                    continue
                if rep_msg['quantity'] > 0:
                    o['quantity'] = rep_msg['quantity']
                for f in ('limit_price', 'stop_price', 'take_profit', 'stop_loss'):
                    if rep_msg[f]:
                        o[f] = rep_msg[f]
                rep(o['intent_id'], o['instrument'], o['side'], NEW, 0.0, 0.0)
            self._handled()

    def wait_for(self, count, timeout=5.0):
        """Block until count messages have arrived. A replay needs this so an
        order is resting before the next bar is marked; a live feed, with a
        bar every minute or more, does not."""
        with self._lock:
            if not self._lock.wait_for(lambda: self.received >= count, timeout):
                raise TimeoutError(f'{self.received} of {count} relay messages arrived')

    @staticmethod
    def _price(o, bar):
        buy = o['side'] == BUY
        if o['order_type'] == MARKET:
            return bar['open']
        if o['order_type'] == LIMIT:
            px = o['limit_price']
            if buy and bar['low'] <= px:
                return min(bar['open'], px)
            if not buy and bar['high'] >= px:
                return max(bar['open'], px)
        if o['order_type'] == STOP:
            px = o['stop_price']
            if buy and bar['high'] >= px:
                return max(bar['open'], px)
            if not buy and bar['low'] <= px:
                return min(bar['open'], px)
        return None

    def mark(self, instrument, bar):
        """Fill what this bar reaches. bar holds open, high, low, close, ts."""
        with self._lock:
            keep, armed, gone, flat = [], [], set(), False
            # Stops before take profits, so a bar reaching both stops out.
            for item in sorted(self._resting, key=lambda i: i[0]['order_type'] != STOP):
                o, report = item
                if o['intent_id'] in gone or (flat and is_exit(o['intent_id'])
                                              and o['instrument'] == instrument):
                    continue                      # its partner exit or a close just filled
                px = self._price(o, bar) if o['instrument'] == instrument else None
                if px is None:
                    keep.append(item)
                    continue
                report(o['intent_id'], instrument, o['side'], FILLED, o['quantity'], px)
                self.fills.append((o['intent_id'], instrument, o['side'], o['quantity'],
                                   px, int(bar['ts'])))
                if is_exit(o['intent_id']) or o['is_close']:
                    flat = True       # the position is closed, so its exits go with it
                    if o.get('linked_intent_id'):
                        gone.add(o['linked_intent_id'])
                else:
                    armed += self._exits(o, report)
            self._resting = [i for i in keep + armed if i[0]['intent_id'] not in gone
                             and not (flat and is_exit(i[0]['intent_id'])
                                      and i[0]['instrument'] == instrument)]

    @staticmethod
    def _exits(o, report):
        side = SELL if o['side'] == BUY else BUY
        legs = [(':tp', LIMIT, o['take_profit']), (':sl', STOP, o['stop_loss'])]
        ids = [o['intent_id'] + suffix for suffix, _, px in legs if px]
        out = []
        for suffix, kind, px in legs:
            if px:
                me = o['intent_id'] + suffix
                out.append([{'intent_id': me, 'instrument': o['instrument'],
                             'side': side, 'order_type': kind, 'quantity': o['quantity'],
                             'limit_price': px if kind == LIMIT else 0.0,
                             'stop_price': px if kind == STOP else 0.0,
                             'is_close': True, 'parent': o['intent_id'],
                             'linked_intent_id': next((i for i in ids if i != me), '')},
                            report])
        return out
