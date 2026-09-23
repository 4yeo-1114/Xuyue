# -*- coding: utf-8 -*-
"""原始 socket 探针：绕过 psycopg2 的编码问题，直接走 PG wire protocol。
诊断连接/认证失败的真实原因（GBK 解码），成功后列出表。用完即删。"""
import socket, struct, hashlib

HOST = "192.168.1.199"
PORT = 5432
USER = "postgres"
PASSWORD = "postgres"
DB = "grade"


def md5hex(b):
    return hashlib.md5(b).hexdigest()


def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise EOFError("connection closed")
        buf += chunk
    return buf


def read_msg(s):
    hdr = recv_exact(s, 5)
    typ = hdr[0:1]
    length = struct.unpack("!I", hdr[1:5])[0]
    payload = recv_exact(s, length - 4)
    return typ, payload


def send_msg(s, typ, payload):
    s.sendall(typ + struct.pack("!I", len(payload) + 4) + payload)


def parse_error(payload):
    fields = {}
    i = 0
    while i < len(payload) and payload[i] != 0:
        code = payload[i:i + 1].decode()
        i += 1
        j = payload.index(b"\x00", i)
        fields[code] = payload[i:j]
        i = j + 1
    return fields


def main():
    s = socket.create_connection((HOST, PORT), timeout=10)
    params = [("user", USER), ("database", DB), ("client_encoding", "UTF8")]
    body = struct.pack("!I", 196608)
    for k, v in params:
        body += k.encode() + b"\x00" + v.encode() + b"\x00"
    body += b"\x00"
    send_msg(s, b"", body)

    auth_done = False
    while True:
        typ, payload = read_msg(s)
        if typ == b"R":
            code = struct.unpack("!I", payload[:4])[0]
            if code == 0:
                print("AUTH: ok")
                auth_done = True
            elif code == 5:
                salt = payload[4:8]
                inner = md5hex((PASSWORD + USER).encode())
                outer = md5hex(inner.encode() + salt)
                send_msg(s, b"p", ("md5" + outer).encode() + b"\x00")
                print("AUTH: sent md5 response (password=%s)" % PASSWORD)
            else:
                print("AUTH: unsupported code", code)
                return
        elif typ == b"E":
            fields = parse_error(payload)
            print("ERROR (raw fields):")
            for code, val in fields.items():
                print("   [%s] %s" % (code, val.decode("gbk", errors="replace")))
            return
        elif typ == b"Z":
            print("ReadyForQuery status=%r" % payload[0:1])
            break
        elif typ == b"S":
            i = payload.index(b"\x00")
            key = payload[:i].decode()
            val = payload[i + 1:-1].decode("gbk", errors="replace")
            print("ParamStatus %s = %s" % (key, val))
        elif typ == b"K":
            print("BackendKeyData", struct.unpack("!II", payload))
        elif typ == b"N":
            print("Notice:", parse_error(payload))
        else:
            print("Other", typ, payload[:100])

    if not auth_done:
        return

    q = ("select table_schema, table_name from information_schema.tables "
         "where table_schema not in ('pg_catalog','information_schema') "
         "order by 1,2")
    send_msg(s, b"Q", q.encode() + b"\x00")
    ncols = 0
    rows = []
    while True:
        typ, payload = read_msg(s)
        if typ == b"T":
            ncols = struct.unpack("!H", payload[:2])[0]
        elif typ == b"D":
            vals = []
            i = 2
            for _ in range(ncols):
                ln = struct.unpack("!i", payload[i:i + 4])[0]
                i += 4
                if ln == -1:
                    vals.append(None)
                else:
                    vals.append(payload[i:i + ln].decode("utf8", errors="replace"))
                    i += ln
            rows.append(vals)
        elif typ == b"C":
            i = payload.index(b"\x00")
            print("CommandComplete:", payload[:i].decode())
        elif typ == b"E":
            fields = parse_error(payload)
            print("QUERY ERROR:")
            for code, val in fields.items():
                print("   [%s] %s" % (code, val.decode("gbk", errors="replace")))
            return
        elif typ == b"Z":
            break
        else:
            print("Other", typ, payload[:100])

    print("TABLES (%d):" % len(rows))
    for r in rows:
        print("   ", r[0], ".", r[1])
    s.close()


if __name__ == "__main__":
    main()
