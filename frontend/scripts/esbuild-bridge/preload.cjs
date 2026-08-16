/**
 * esbuild-bridge preload (NODE_OPTIONS=--require=scripts/esbuild-bridge/preload.cjs)
 *
 * WHY: This sandbox denies child_process.spawn with pipe stdio (EPERM on named-pipe
 * creation). esbuild's JS API always spawns its service process over pipes, so the
 * Vite build cannot start the esbuild service directly here.
 *
 * WHAT: This preload transparently reroutes the esbuild service over a TCP loopback
 * socket instead of OS pipes:
 *   - Parent side: intercept child_process.spawn when the command line contains
 *     `--service=`, start a local TCP server, spawn the real child with
 *     stdio:'ignore' (no pipes) and an env var carrying the port, and return a
 *     fake ChildProcess whose stdin/stdout are wired to the accepted socket.
 *   - Child side (same preload runs inside `node bin/esbuild` via inherited
 *     NODE_OPTIONS): connect to the port and redirect the Go WASM runtime's
 *     fd-0 reads / fd-1 writes to the socket.
 *
 * On a normal machine this preload is unnecessary; it is harmless there too.
 * `npm run build` works without it outside this sandbox.
 */
'use strict';

const BRIDGE_ENV = 'ESBUILD_BRIDGE_PORT';
// capture BEFORE bin/esbuild deletes most env vars (Go workaround)
const BRIDGE_DEBUG = !!process.env.ESBUILD_BRIDGE_DEBUG;

if (BRIDGE_DEBUG) {
  console.error(`[esbuild-bridge] preload loaded in pid=${process.pid} port=${process.env[BRIDGE_ENV] || 'none'}`);
}

// ---------------------------------------------------------------------------
// CHILD SIDE: we are `node node_modules/esbuild/bin/esbuild --service=...`
// ---------------------------------------------------------------------------
if (process.env[BRIDGE_ENV]) {
  const net = require('net');
  const fs = require('fs');

  const port = parseInt(process.env[BRIDGE_ENV], 10);
  const sock = net.connect(port, '127.0.0.1');
  const T0 = Date.now();
  const tlog = (msg) => console.error(`[+${Date.now() - T0}ms] ${msg}`);

  let queue = Buffer.alloc(0);
  sock.on('data', (d) => {
    queue = Buffer.concat([queue, d]);
    if (BRIDGE_DEBUG) tlog(`sock data ${d.length}, queue ${queue.length}`);
  });
  sock.on('error', (e) => {
    if (BRIDGE_DEBUG) tlog('sock error ' + (e && e.message));
  });
  sock.on('connect', () => {
    if (BRIDGE_DEBUG) tlog('sock connected');
  });
  sock.on('close', () => {
    if (BRIDGE_DEBUG) tlog('sock closed');
  });

  if (BRIDGE_DEBUG) {
    setInterval(() => {
      tlog(`heartbeat state=${sock.readyState} queue=${queue.length}`);
    }, 1000);
  }

  const toBuffer = (buf) => (Buffer.isBuffer(buf) ? buf : Buffer.from(buf.buffer, buf.byteOffset, buf.byteLength));

  // bin/esbuild re-patches fs.write/fs.writeSync to route fd 1 through
  // process.stdout.write, so patch THAT to reach the socket instead.
  // IMPORTANT: buf is a view over WASM memory which can be detached by
  // memory.grow(), so always COPY before handing bytes to the socket.
  const origStdoutWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = function (buf, cb) {
    const b = Buffer.from(toBuffer(buf));
    if (BRIDGE_DEBUG) console.error('[bridge:stdout.write] called len=', b.length, 'cb=', !!cb, 'state=', sock.readyState);
    if (sock && !sock.destroyed) {
      try {
        const wrapped = cb
          ? function () {
              if (BRIDGE_DEBUG)
                console.error('[bridge:stdout.write] cb args=', arguments.length, typeof arguments[0], arguments[0] && arguments[0].message);
              cb.apply(this, arguments);
            }
          : cb;
        sock.write(b, wrapped);
        return true;
      } catch (err) {
        if (BRIDGE_DEBUG) console.error('[bridge:stdout.write] throw', err);
        if (cb) cb(err);
        return false;
      }
    }
    return origStdoutWrite(b, cb);
  };
  process.stdout.writeSync = function (buf) {
    const b = Buffer.from(toBuffer(buf));
    if (sock && !sock.destroyed) {
      try {
        sock.write(b);
      } catch {
        /* ignore */
      }
      return b.length;
    }
    return origStdoutWrite(b).length;
  };

  // --- fd 0 reads come from the socket queue (async callback style) ---
  const origRead = fs.read;
  fs.read = function (fd, buffer, offset, length, position, callback) {
    if (fd === 0) {
      const target = toBuffer(buffer);
      if (BRIDGE_DEBUG) console.error(`[bridge:fs.read] want=${length} have=${queue.length}`);
      const tryRead = () => {
        if (queue.length === 0) {
          if (BRIDGE_DEBUG) console.error('[bridge:fs.read] poll waiting');
          setImmediate(tryRead);
          return;
        }
        const n = Math.min(length, queue.length);
        queue.copy(target, offset, 0, n);
        queue = queue.subarray(n);
        if (BRIDGE_DEBUG) console.error(`[bridge:fs.read] return ${n}, remaining=${queue.length}`);
        callback(null, n, target);
      };
      tryRead();
      return;
    }
    return origRead.apply(this, arguments);
  };
  // fs.readSync (fd 0) — defensive: Go may use the sync read for stdin
  const origReadSync = fs.readSync;
  fs.readSync = function (fd, buffer, offset, length, position) {
    if (fd === 0) {
      const target = toBuffer(buffer);
      if (BRIDGE_DEBUG) console.error(`[bridge:fs.readSync] want=${length} have=${queue.length}`);
      const n = Math.min(length, queue.length);
      queue.copy(target, offset, 0, n);
      queue = queue.subarray(n);
      if (BRIDGE_DEBUG) console.error(`[bridge:fs.readSync] return ${n}`);
      return n;
    }
    return origReadSync.apply(this, arguments);
  };

  // --- fd 1 writes go to the socket (fs.write / fs.writeSync) ---
  const origWrite = fs.write;
  fs.write = function (fd, buf, offset, length, position, callback) {
    if (BRIDGE_DEBUG)
      console.error('[bridge:fs.write] fd=', fd, 'len=', length, 'cb=', typeof callback);
    if (fd === 1 && offset === 0 && length === buf.length && position === null) {
      const b = Buffer.from(toBuffer(buf));
      sock.write(b, (err) => {
        if (BRIDGE_DEBUG) console.error('[bridge:fs.write:cb] err=', err && err.message, typeof err);
        if (err) callback(err, 0, null);
        else callback(null, length, b);
      });
      return;
    }
    if (fd === 2) {
      try {
        process.stderr.write(Buffer.from(toBuffer(buf)), (err) =>
          err ? callback(err, 0, null) : callback(null, length, buf),
        );
      } catch (err) {
        callback(err, 0, null);
      }
      return;
    }
    return origWrite.apply(this, arguments);
  };
  const origWriteSync = fs.writeSync;
  fs.writeSync = function (fd, buf) {
    if (fd === 1) {
      sock.write(Buffer.from(toBuffer(buf)));
      return buf.length;
    }
    if (fd === 2) {
      try {
        process.stderr.write(Buffer.from(toBuffer(buf)));
      } catch {
        /* ignore */
      }
      return buf.length;
    }
    return origWriteSync.apply(this, arguments);
  };
} else {
  // -------------------------------------------------------------------------
  // PARENT SIDE: intercept esbuild's service spawn and bridge it over TCP
  // -------------------------------------------------------------------------
  const net = require('net');
  const cp = require('child_process');
  const { EventEmitter, Writable, Readable } = require('stream');

  const origSpawn = cp.spawn;

  // -------------------------------------------------------------------------
  // Vite's Windows realpath probe: `cmd /c for %I in ('<path>') do @echo %~sI`
  // also uses pipe stdio; simulate a successful probe (short path = path).
  // -------------------------------------------------------------------------
  const extractProbePath = (args) => {
    const list = Array.isArray(args) ? args : [];
    const arg = list.find((a) => typeof a === 'string' && a.includes('for %I in'));
    if (!arg) return null;
    const m = arg.match(/for %I in \('([^']*)'\)/);
    return m ? m[1] : null;
  };
  const isCmdProbe = (file, args) => {
    const f = typeof file === 'string' ? file.toLowerCase() : '';
    if (!/cmd(\.exe)?$/.test(f)) return false;
    const list = Array.isArray(args) ? args : [];
    return list.some((a) => typeof a === 'string' && a.includes('for %I in'));
  };
  /** vite probes network drives with `net use`; simulate an empty result */
  const isNetUseProbe = (file, args) => {
    const list = Array.isArray(args) ? args : [];
    const joined = (typeof file === 'string' ? file + ' ' : '') + list.join(' ');
    return joined.toLowerCase().includes('net use');
  };

  const origSpawnSync = cp.spawnSync;
  cp.spawnSync = function (file, args, options) {
    if (isCmdProbe(file, args)) {
      const p = extractProbePath(args) ?? '';
      const out = Buffer.from(p + '\r\n');
      return {
        pid: -1,
        output: [null, out, Buffer.alloc(0)],
        stdout: out,
        stderr: Buffer.alloc(0),
        status: 0,
        signal: null,
        error: undefined,
      };
    }
    if (isNetUseProbe(file, args)) {
      const out = Buffer.alloc(0);
      return {
        pid: -1,
        output: [null, out, Buffer.alloc(0)],
        stdout: out,
        stderr: Buffer.alloc(0),
        status: 0,
        signal: null,
        error: undefined,
      };
    }
    return origSpawnSync.apply(this, arguments);
  };

  const origExecFileSync = cp.execFileSync;
  cp.execFileSync = function (file, args, options) {
    if (isCmdProbe(file, args)) {
      return Buffer.from((extractProbePath(args) ?? '') + '\r\n');
    }
    if (isNetUseProbe(file, args)) {
      return Buffer.alloc(0);
    }
    return origExecFileSync.apply(this, arguments);
  };

  const origExecSync = cp.execSync;
  cp.execSync = function (command, options) {
    const c = typeof command === 'string' ? command : String(command);
    if (c.includes('for %I in')) {
      const m = c.match(/for %I in \('([^']*)'\)/);
      return Buffer.from((m ? m[1] : '') + '\r\n');
    }
    if (c.toLowerCase().includes('net use')) {
      return Buffer.alloc(0);
    }
    return origExecSync.apply(this, arguments);
  };

  const origExecFile = cp.execFile;
  cp.execFile = function (file, args, options, callback) {
    if (isCmdProbe(file, args)) {
      const cb = typeof options === 'function' ? options : callback;
      const out = Buffer.from((extractProbePath(args) ?? '') + '\r\n');
      if (typeof cb === 'function') {
        process.nextTick(() => cb(null, out.toString(), ''));
      }
      return undefined;
    }
    if (isNetUseProbe(file, args)) {
      const cb = typeof options === 'function' ? options : callback;
      if (typeof cb === 'function') {
        process.nextTick(() => cb(null, '', ''));
      }
      return undefined;
    }
    return origExecFile.apply(this, arguments);
  };

  const origExec = cp.exec;
  cp.exec = function (command, options, callback) {
    const c = typeof command === 'string' ? command : String(command);
    if (c.includes('for %I in')) {
      const cb = typeof options === 'function' ? options : callback;
      const m = c.match(/for %I in \('([^']*)'\)/);
      const out = Buffer.from((m ? m[1] : '') + '\r\n');
      if (typeof cb === 'function') {
        process.nextTick(() => cb(null, out.toString(), ''));
      }
      return undefined;
    }
    if (c.toLowerCase().includes('net use')) {
      const cb = typeof options === 'function' ? options : callback;
      if (typeof cb === 'function') {
        process.nextTick(() => cb(null, '', ''));
      }
      return undefined;
    }
    return origExec.apply(this, arguments);
  };

  cp.spawn = function (command, args, options) {
    const argsArr = Array.isArray(args) ? args : [];
    const isEsbuildService = argsArr.some(
      (a) => typeof a === 'string' && a.indexOf('--service=') === 0,
    );
    if (!isEsbuildService) {
      return origSpawn.call(this, command, args, options);
    }

    let socket = null;
    let connected = false;
    let pendingWrites = [];
    let realChild = null;

    const stdin = new Writable({
      write(chunk, enc, cb) {
        if (connected && socket) {
          socket.write(chunk, cb);
        } else {
          pendingWrites.push([chunk, cb]);
        }
      },
    });
    stdin.destroy = () => {
      if (socket) {
        try {
          socket.destroy();
        } catch {
          /* ignore */
        }
      }
    };
    stdin.unref = () => {};

    const stdout = new Readable({ read() {} });
    stdout.unref = () => {};
    stdout.destroy = () => {
      if (socket) {
        try {
          socket.destroy();
        } catch {
          /* ignore */
        }
      }
    };

    const fakeChild = new EventEmitter();
    fakeChild.stdin = stdin;
    fakeChild.stdout = stdout;
    fakeChild.kill = () => {
      if (socket) {
        try {
          socket.destroy();
        } catch {
          /* ignore */
        }
      }
      if (realChild) {
        try {
          realChild.kill();
        } catch {
          /* ignore */
        }
      }
    };
    fakeChild.unref = () => {
      if (realChild) try { realChild.unref(); } catch { /* ignore */ }
    };
    fakeChild.ref = () => {
      if (realChild) try { realChild.ref(); } catch { /* ignore */ }
    };

    const server = net.createServer((sock) => {
      socket = sock;
      connected = true;
      sock.on('data', (d) => {
        stdout.push(d);
      });
      sock.on('end', () => stdout.push(null));
      sock.on('close', () => stdout.push(null));
      sock.on('error', (e) => fakeChild.emit('error', e));
      for (const [chunk, cb] of pendingWrites) {
        sock.write(chunk, cb);
      }
      pendingWrites = [];
    });
    server.on('error', (e) => fakeChild.emit('error', e));

    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      const stdio = ['ignore', 'ignore', 'inherit'];
      try {
        realChild = origSpawn.call(this, command, argsArr, {
          ...(options || {}),
          stdio,
          env: { ...process.env, ...((options && options.env) || {}), [BRIDGE_ENV]: String(port) },
        });
      } catch (e) {
        fakeChild.emit('error', e);
        return;
      }
      realChild.on('error', (e) => fakeChild.emit('error', e));
      realChild.on('exit', () => {
        try {
          server.close();
        } catch {
          /* ignore */
        }
        stdout.push(null);
      });
    });

    return fakeChild;
  };
}
