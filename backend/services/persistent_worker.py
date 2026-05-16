import sys
import json
import io
import contextlib
import traceback

MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB safety cap

def main():
    real_stdout = sys.stdout
    real_stdin = sys.stdin.buffer  # Use binary for chunked reads

    while True:
        try:
            # Chunked protocol: first line is byte length, then read exact bytes
            header = real_stdin.readline()
            if not header:
                break

            header_str = header.decode("utf-8", errors="replace").strip()
            if not header_str.isdigit():
                # Fallback: treat the header itself as a JSON line (backward compat)
                payload_str = header_str
            else:
                payload_size = int(header_str)
                if payload_size > MAX_PAYLOAD_BYTES:
                    err_payload = {"success": False, "stdout": "", "stderr": f"Payload too large ({payload_size} bytes, max {MAX_PAYLOAD_BYTES})"}
                    real_stdout.write(json.dumps(err_payload) + "\n")
                    real_stdout.flush()
                    # Drain the oversized payload
                    remaining = payload_size
                    while remaining > 0:
                        chunk = real_stdin.read(min(remaining, 65536))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                    continue

                raw = b""
                while len(raw) < payload_size:
                    chunk = real_stdin.read(payload_size - len(raw))
                    if not chunk:
                        break
                    raw += chunk
                payload_str = raw.decode("utf-8", errors="replace")

            payload = json.loads(payload_str)
            code = payload.get("code", "")

            out = io.StringIO()
            err = io.StringIO()

            env = {}  # Isolated namespace per execution
            success = False

            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    exec(code, env)
                    success = True
                except Exception:
                    traceback.print_exc(file=err)

            r = {
                "success": success,
                "stdout": out.getvalue(),
                "stderr": err.getvalue()
            }
            real_stdout.write(json.dumps(r) + "\n")
            real_stdout.flush()
        except Exception as e:
            err_payload = {"success": False, "stdout": "", "stderr": str(e) + "\n" + traceback.format_exc()}
            real_stdout.write(json.dumps(err_payload) + "\n")
            real_stdout.flush()

if __name__ == "__main__":
    main()
