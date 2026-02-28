# Full Stack Internals: From HTTP Request to Electrons

**Part 6 of 6: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [The 8-Layer Stack](#1-the-8-layer-stack)
3. [Layer 1: Electrons and Signals on the Wire](#2-layer-1-electrons-and-signals-on-the-wire)
4. [Layer 2: The Network Interface Card (NIC)](#3-layer-2-the-network-interface-card-nic)
5. [Layer 3: OS Kernel — TCP/IP Stack](#4-layer-3-os-kernel--tcpip-stack)
6. [Layer 4: OS Kernel — Socket API and I/O Multiplexing](#5-layer-4-os-kernel--socket-api-and-io-multiplexing)
7. [Layer 5: Python — Sockets and the Event Loop](#6-layer-5-python--sockets-and-the-event-loop)
8. [Layer 6: uvicorn — HTTP Parsing and ASGI Bridge](#7-layer-6-uvicorn--http-parsing-and-asgi-bridge)
9. [Layer 7: Starlette and FastAPI](#8-layer-7-starlette-and-fastapi)
10. [Layer 8: Your Application Code](#9-layer-8-your-application-code)
11. [Complete Round-Trip: All 8 Layers](#10-complete-round-trip-all-8-layers)
12. [Where Time Is Actually Spent](#11-where-time-is-actually-spent)
13. [What File Descriptors Actually Are](#12-what-file-descriptors-actually-are)
14. [uvloop vs asyncio: Why uvicorn Prefers uvloop](#13-uvloop-vs-asyncio-why-uvicorn-prefers-uvloop)
15. [TCP Flow Control and Congestion Control](#14-tcp-flow-control-and-congestion-control)
16. [The Accept Queue: SYN Queue and Completed Queue](#15-the-accept-queue-syn-queue-and-completed-queue)
17. [Keep-Alive Connections](#16-keep-alive-connections)
18. [Summary](#17-summary)

---

## Learning Objectives

After reading this document, you will understand:

- What physically happens to **electrons and electrical signals** when a client sends an HTTP request
- How the **NIC (Network Interface Card)** converts signals to bytes using **DMA (Direct Memory Access)** — writing to RAM without the CPU
- How the **OS kernel** reassembles TCP segments, manages socket buffers, and wakes up your Python process via **kqueue/epoll**
- What a **file descriptor** actually is — an index into a kernel table
- How **uvicorn creates a server socket** and what each syscall does
- How **httptools** (C-level HTTP parser) converts raw bytes to structured request data
- How **Starlette routes and FastAPI dispatches** the request to your endpoint
- Where time is **actually spent** across all layers for an AI Doctor briefing request

Key mental models to internalize:

- **Data doesn't "travel" — signals propagate.** An HTTP request is electrical voltage changes on copper, light pulses in fiber, or radio waves in WiFi. The "data" is a pattern imposed on those signals.
- **The CPU is rarely involved in I/O.** The NIC uses DMA to write incoming data directly to RAM. The CPU only gets involved when the kernel interrupt handler runs and when your Python code processes the data.
- **The kernel is a mediator.** It manages hardware, enforces isolation between processes, reassembles network data, and provides the socket API that Python calls.
- **Most of your server's time is spent doing nothing.** During an 8-second agent call, the CPU does ~0.2ms of actual work. The rest is waiting — and waiting is free with async.

---

## 1. The 8-Layer Stack

Every HTTP request to your FastAPI server passes through all of these layers:

```
Layer 8  │  Your Code        │  async def create_briefing() — business logic
Layer 7  │  FastAPI/Starlette│  Routing, validation, dependency injection, serialization
Layer 6  │  uvicorn          │  HTTP parser (httptools/C), ASGI protocol bridge
Layer 5  │  Python/Event Loop│  asyncio/uvloop, socket module, coroutine scheduling
Layer 4  │  Kernel: I/O Mux  │  kqueue (macOS) / epoll (Linux) — FD monitoring
Layer 3  │  Kernel: TCP/IP   │  TCP reassembly, IP routing, socket buffers
Layer 2  │  NIC (Hardware)   │  DMA, interrupt generation, frame CRC checks
Layer 1  │  Wire/Radio       │  Electrons (copper), photons (fiber), radio waves (WiFi)
```

We'll trace a single request from the bottom up: from physical signals to your Python code. Then we'll follow the response back down.

---

## 2. Layer 1: Electrons and Signals on the Wire

### What physically happens when a client sends a request

When a browser sends `POST /api/patients/1/briefing` to your server, the "data" starts as **electrical signals**. The medium depends on the connection type.

### Ethernet (copper cable — office/data center)

Ethernet uses **differential signaling** on twisted-pair copper cables. Each bit is encoded as a voltage difference between two wires:

```
         Voltage
           │
    +1V ───┤     ┌───┐     ┌───┐     ┌───┐
           │     │   │     │   │     │   │
    0V  ───┤─────┘   └─────┘   └─────┘   └─────
           │
   -1V ───┤
           └──────────────────────────────────── Time
                  1   0     1   0     1   0

           Example: Manchester encoding (simplified)
           Real Gigabit Ethernet uses PAM-5 with 4 pairs
```

At Gigabit Ethernet speeds, each voltage transition happens every **8 nanoseconds** (125 million symbols per second, on each of 4 wire pairs). Your HTTP request — say 500 bytes of headers + JSON body — is encoded as roughly **4,000 voltage transitions** that propagate down the cable at about **2/3 the speed of light** (~200,000 km/s in copper).

For `localhost` (loopback): no physical wire is involved. The kernel copies data between socket buffers directly in RAM. The "signal" is just a memory write.

### WiFi (radio waves — laptop)

On WiFi, the same data is encoded as **radio frequency modulation**:

```
        Amplitude/Phase
           │
           │    ╱╲    ╱╲
           │   ╱  ╲  ╱  ╲     ← carrier wave (~5 GHz for WiFi 5/6)
           │  ╱    ╲╱    ╲
           │─────────────────── Time
           │
           │  Data is encoded by shifting the PHASE and AMPLITUDE
           │  of the carrier wave (QAM modulation)
           │
           │  WiFi 6 (802.11ax): 1024-QAM
           │  = 10 bits per symbol per subcarrier
           │  = 500 bytes takes ~0.004ms over the air
```

The WiFi radio in your laptop modulates a 5 GHz carrier wave. The access point's radio demodulates it, extracts the Ethernet frame, and forwards it to the wired network (or loopback if same machine).

### Fiber optic (photons — data center/internet backbone)

For requests crossing the internet (e.g., to Claude's API):

```
        Light intensity
           │
    ON  ───┤  █   █ █   █ █ █   █
           │  █   █ █   █ █ █   █
   OFF  ───┤──  ─   ──  ─       ──── Time
           │
           │  Laser pulses in glass fiber
           │  Speed: ~200,000 km/s (speed of light in glass)
           │  100 Gbps = 10 billion pulses per second
```

A laser at one end of the fiber pulses on and off. A photodetector at the other end reads the pulses. Each pulse is a few nanoseconds. The light bounces along the fiber core via **total internal reflection**.

### The key physical insight

At every layer, "data" is just a **pattern imposed on a physical medium**:
- Copper: voltage pattern
- Fiber: light pulse pattern
- WiFi: radio wave modulation pattern
- RAM: charge pattern in capacitors (DRAM cells)

The pattern is the same at every layer — it's the **encoding** that changes.

---

## 3. Layer 2: The Network Interface Card (NIC)

### What the NIC does

The NIC is the hardware that converts between physical signals (Layer 1) and digital data (bytes in RAM). It's the boundary between the physical world and the computer's memory.

```
                     NIC (Network Interface Card)
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  PHY (Physical Layer Chip)        MAC (Media Access Ctrl)  │
│  ┌──────────────────────┐        ┌──────────────────────┐  │
│  │ Receives electrical   │        │ Checks CRC (frame    │  │
│  │ signals from wire     │ ─────→ │ integrity)           │  │
│  │                       │        │                      │  │
│  │ Converts to digital   │        │ Strips Ethernet      │  │
│  │ bits (ADC/CDR)        │        │ header/trailer       │  │
│  │                       │        │                      │  │
│  │ Clock recovery:       │        │ Writes payload to    │  │
│  │ syncs to signal       │        │ ring buffer in RAM   │──── DMA
│  │ timing                │        │ via DMA              │  │
│  └──────────────────────┘        └──────────────────────┘  │
│                                                            │
│                    Raises hardware INTERRUPT ───────────────── → CPU
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### DMA: Direct Memory Access — the NIC writes to RAM without the CPU

This is one of the most important hardware concepts for understanding server performance. The NIC does **not** send data through the CPU. Instead:

```
                     System RAM
                    ┌──────────────────────────────────┐
                    │                                  │
                    │   Ring Buffer (RX descriptor ring)│
                    │   ┌────────────────────────────┐ │
                    │   │ Slot 0: [Ethernet frame 1] │ │ ← NIC writes here directly
                    │   │ Slot 1: [Ethernet frame 2] │ │ ← via DMA (no CPU involved)
                    │   │ Slot 2: [empty]            │ │
                    │   │ Slot 3: [empty]            │ │
                    │   │ ...                        │ │
                    │   └────────────────────────────┘ │
                    │                                  │
                    │   NIC writes frame → raises IRQ  │
                    │   CPU reads from ring buffer     │
                    │   (only AFTER interrupt)          │
                    └──────────────────────────────────┘
```

1. The OS driver allocates a **ring buffer** in RAM and gives the NIC its physical address
2. When a frame arrives, the NIC's DMA engine copies it directly into the next ring buffer slot
3. The NIC then raises a **hardware interrupt** (IRQ) to notify the CPU
4. The CPU was doing other work (or sleeping) — now it handles the interrupt

**Why this matters for servers:** The CPU is free to run Python code, process other requests, or even sleep. Network data arrives into RAM without any CPU involvement. The CPU only gets involved when it processes the interrupt — and on a busy server, interrupts are batched (NAPI on Linux) so one interrupt handles many frames.

### The interrupt — how hardware talks to the CPU

When the NIC raises an interrupt:

```
NIC                          CPU                          OS Kernel
───                          ───                          ─────────

Raises IRQ on ──────────→  CPU stops whatever it
interrupt line               was executing (even
                             mid-Python-instruction)

                             Saves register state
                             (program counter, stack
                             pointer, flags)

                             Jumps to interrupt ──────→  NIC interrupt handler:
                             vector table entry           1. Read frames from ring buffer
                                                          2. Allocate sk_buff (socket buffer)
                                                          3. Parse Ethernet header
                                                          4. Pass to IP layer
                                                          5. Acknowledge interrupt

                             Restores register  ←──────  Handler returns
                             state

                             Resumes whatever it
                             was doing (Python
                             bytecode, sleep, etc.)
```

This entire interrupt handling takes **microseconds**. Your Python code doesn't know it happened — from Python's perspective, it just takes slightly longer to execute the current instruction.

---

## 4. Layer 3: OS Kernel — TCP/IP Stack

### From raw bytes to a TCP stream

After the NIC interrupt handler passes the frame to the kernel's network stack, the data travels through multiple protocol layers — all within the kernel, in C code, very fast:

```
Ethernet frame from NIC ring buffer
│
▼
┌──────────────────────────────────────────────────────────────────┐
│  ETHERNET LAYER                                                  │
│  ┌──────────┬───────────────────────────────────┬──────────────┐ │
│  │ Eth Hdr  │ Payload (IP packet)               │ CRC (4B)    │ │
│  │ (14B)    │                                   │             │ │
│  │ dst MAC  │                                   │ (already    │ │
│  │ src MAC  │                                   │  verified   │ │
│  │ type:    │                                   │  by NIC)    │ │
│  │ 0x0800   │                                   │             │ │
│  │ (= IPv4) │                                   │             │ │
│  └──────────┴───────────────────────────────────┴──────────────┘ │
│  Kernel strips Ethernet header, passes payload to IP layer       │
└──────────────────────────────────────────────────────────────────┘
│
▼
┌──────────────────────────────────────────────────────────────────┐
│  IP LAYER                                                        │
│  ┌──────────┬───────────────────────────────────┐                │
│  │ IP Hdr   │ Payload (TCP segment)             │                │
│  │ (20B)    │                                   │                │
│  │ src IP:  │                                   │                │
│  │ 10.0.1.5 │                                   │                │
│  │ dst IP:  │                                   │                │
│  │ 10.0.1.1 │                                   │                │
│  │ proto:   │                                   │                │
│  │ 6 (TCP)  │                                   │                │
│  └──────────┴───────────────────────────────────┘                │
│  Kernel checks: is dst IP ours? Yes → pass to TCP layer          │
│  (If not ours and IP forwarding enabled → route to next hop)     │
└──────────────────────────────────────────────────────────────────┘
│
▼
┌──────────────────────────────────────────────────────────────────┐
│  TCP LAYER                                                       │
│  ┌──────────┬───────────────────────────────────┐                │
│  │ TCP Hdr  │ Payload (HTTP data)               │                │
│  │ (20B+)   │                                   │                │
│  │ src port:│ "POST /api/patients/1/briefing    │                │
│  │ 52341    │  HTTP/1.1\r\nHost: ..."           │                │
│  │ dst port:│                                   │                │
│  │ 8000     │                                   │                │
│  │ seq: 1001│                                   │                │
│  │ ack: 5001│                                   │                │
│  │ flags:   │                                   │                │
│  │ PSH,ACK  │                                   │                │
│  └──────────┴───────────────────────────────────┘                │
│                                                                  │
│  Kernel TCP state machine:                                       │
│  1. Look up socket by (dst_ip, dst_port, src_ip, src_port)      │
│  2. Check sequence number — is this the next expected segment?   │
│  3. If yes: append payload to socket RECEIVE BUFFER              │
│  4. If out of order: store in out-of-order queue, send dup ACK   │
│  5. Send ACK back to client (may be delayed/batched)             │
│  6. Wake up any process waiting on this socket's data            │
└──────────────────────────────────────────────────────────────────┘
```

### Socket buffers — the kernel-managed queues

Each TCP connection has two buffers managed entirely by the kernel:

```
        Socket (kernel struct, per TCP connection)
       ┌──────────────────────────────────────────────────┐
       │                                                  │
       │  RECEIVE BUFFER (incoming data from client)      │
       │  ┌────────────────────────────────────────────┐  │
       │  │ "POST /api/patients/1/briefing HTTP/1.1\r  │  │
       │  │ \nHost: localhost:8000\r\nContent-Type:     │  │
       │  │ application/json\r\n\r\n{\"notes\":\"...\"}" │  │
       │  └────────────────────────────────────────────┘  │
       │  Size: configurable, default ~256KB on macOS     │
       │  Written by: kernel TCP layer (from NIC frames)  │
       │  Read by: Python via recv() syscall              │
       │                                                  │
       │  SEND BUFFER (outgoing data to client)           │
       │  ┌────────────────────────────────────────────┐  │
       │  │ (empty — waiting for Python to write       │  │
       │  │  the HTTP response)                        │  │
       │  └────────────────────────────────────────────┘  │
       │  Size: configurable, default ~256KB on macOS     │
       │  Written by: Python via send() syscall           │
       │  Read by: kernel TCP layer (segments to NIC)     │
       │                                                  │
       │  State: ESTABLISHED                              │
       │  Local:  0.0.0.0:8000                            │
       │  Remote: 10.0.1.5:52341                          │
       └──────────────────────────────────────────────────┘
```

The kernel handles **all of the complexity** of TCP:
- **Reassembly**: segments arrive out of order → kernel sorts them by sequence number
- **Retransmission**: if an ACK doesn't arrive within a timeout, kernel resends the segment
- **Flow control**: receive window tells the sender how much buffer space remains
- **Congestion control**: kernel adjusts send rate based on network conditions

Your Python code never sees any of this. It just reads an ordered byte stream from the receive buffer.

---

## 5. Layer 4: OS Kernel — Socket API and I/O Multiplexing

### How Python creates a server socket

When uvicorn starts and calls `socket.socket()`, `bind()`, `listen()`, each Python call maps to a kernel syscall. Here's what happens inside the kernel:

```python
# Python code                       # What the kernel does
# ──────────                        # ────────────────────

sock = socket.socket(                # syscall: socket(AF_INET, SOCK_STREAM, 0)
    socket.AF_INET,                  #
    socket.SOCK_STREAM,              # Kernel allocates:
)                                    #   - struct socket (protocol-independent)
                                     #   - struct sock (TCP-specific state)
                                     #   - file descriptor (integer index)
                                     #   Returns: fd=5 (for example)

sock.setsockopt(                     # syscall: setsockopt(5, SOL_SOCKET, SO_REUSEADDR, 1)
    socket.SOL_SOCKET,               #
    socket.SO_REUSEADDR, 1           # Sets flag so bind() works even if port was
)                                    # recently used (TIME_WAIT sockets from prev run)

sock.bind(("0.0.0.0", 8000))        # syscall: bind(5, {AF_INET, 0.0.0.0, 8000}, 16)
                                     #
                                     # Kernel associates fd=5 with port 8000
                                     # Checks: is port 8000 available? Yes → proceed
                                     # Adds entry to kernel port-to-socket lookup table

sock.listen(128)                     # syscall: listen(5, 128)
                                     #
                                     # Marks socket as PASSIVE (listening)
                                     # Creates TWO queues (see Section 15):
                                     #   - SYN queue (half-open connections, max ~128)
                                     #   - Accept queue (completed connections, max 128)
                                     # Kernel now handles TCP handshakes autonomously

sock.setblocking(False)              # syscall: fcntl(5, F_SETFL, O_NONBLOCK)
                                     #
                                     # Non-blocking mode: recv()/accept() return
                                     # immediately with EAGAIN instead of blocking
                                     # if no data/connection is available
```

### kqueue (macOS) / epoll (Linux) — I/O multiplexing

After creating the socket, the event loop registers it with the OS's I/O multiplexing facility. This is the mechanism that lets one thread monitor thousands of connections:

```
                       Event Loop Startup
                       ──────────────────

# macOS: kqueue                          # Linux: epoll
kq = kqueue()                            epfd = epoll_create1(0)
# Kernel creates a kqueue instance       # Kernel creates an epoll instance
# Returns fd for the kqueue itself       # Returns fd for the epoll instance

# Register interest in server socket     # Register interest in server socket
kevent(kq, [                             epoll_ctl(epfd,
  {ident=5,                                EPOLL_CTL_ADD,
   filter=EVFILT_READ,                     5,  # server socket fd
   flags=EV_ADD}                           {events=EPOLLIN}  # interested in reads
])                                       )

                       Main Loop (runs forever)
                       ────────────────────────

# macOS:                                 # Linux:
events = kevent(kq,                      events = epoll_wait(epfd,
  changelist=None,                         maxevents=1024,
  maxevents=1024,                          timeout=-1)
  timeout=None)                          # ↑ blocks until I/O ready on ANY
# ↑ blocks until I/O ready on ANY       #   registered file descriptor
#   registered file descriptor

# Returns: [{fd=5, filter=READ}]         # Returns: [{fd=5, events=EPOLLIN}]
# Meaning: "server socket has a          # Meaning: same — new connection
#           pending connection"           #          is ready to accept
```

**The critical insight**: `kevent()` / `epoll_wait()` is the **only blocking call** in the entire async Python server. Everything else is non-blocking. When people say "the event loop is idle," the process is blocked inside this one syscall, consuming zero CPU, waiting for the OS kernel to say "something happened on one of your file descriptors."

### What happens inside the kernel during kqueue/epoll

```
Process calls kevent(kq, ..., timeout=NULL)
│
▼
Kernel:
├── Check: any events already pending?
│   ├── Yes → return immediately with event list
│   └── No → put process to sleep on wait queue
│
│   ... time passes, process is sleeping, CPU runs other processes ...
│
├── NIC interrupt fires (new data or connection arrived)
│   ├── Kernel TCP stack processes frame
│   ├── Appends data to socket receive buffer
│   └── Checks: is anyone waiting on this socket via kqueue/epoll?
│       └── Yes → wake up the sleeping process
│
▼
Process wakes up
├── kevent() returns: [{fd=8, filter=READ}]
├── Event loop: "fd 8 is readable"
├── Schedules the corresponding coroutine callback
└── Coroutine resumes, calls recv(fd=8) → gets the data
```

---

## 6. Layer 5: Python — Sockets and the Event Loop

### How asyncio wraps the kernel syscalls

Python's `asyncio` (or `uvloop`) wraps the kqueue/epoll mechanism into a high-level coroutine API. Here's what happens when an `await` touches the network:

```python
# What you write:
data = await loop.sock_recv(client_socket, 65536)

# What actually happens (simplified):
# 1. asyncio registers client_socket.fileno() with kqueue/epoll for READ
# 2. Creates a Future, attaches callback to resume this coroutine
# 3. Returns control to event loop (coroutine is suspended)
# 4. Event loop calls kevent() — blocks until data arrives
# 5. kevent() returns: "fd 8 is readable"
# 6. Event loop calls recv(fd=8, 65536) — non-blocking, returns bytes immediately
# 7. Sets Future result to the bytes
# 8. Schedules coroutine resumption
# 9. Your code continues with data = b"POST /api/patients/..."
```

### The event loop pseudocode (what actually runs)

```python
# This is a simplified version of what asyncio's event loop does.
# The real implementation is in CPython's Lib/asyncio/selector_events.py
# (or in uvloop's Cython/C code).

class EventLoop:
    def __init__(self):
        self._selector = selectors.KqueueSelector()  # or EpollSelector on Linux
        self._ready = deque()        # callbacks ready to run RIGHT NOW
        self._scheduled = []         # callbacks scheduled for a future time

    def run_forever(self):
        while True:
            # 1. Run all ready callbacks (coroutine resumptions, timers)
            while self._ready:
                callback = self._ready.popleft()
                callback()  # This resumes a coroutine or runs a timer

            # 2. Calculate timeout: when is the next scheduled timer?
            timeout = self._calculate_timeout()

            # 3. THE CRITICAL CALL — ask the OS "what's ready?"
            events = self._selector.select(timeout)
            # ↑ This calls kevent() on macOS or epoll_wait() on Linux
            # ↑ This is WHERE THE PROCESS SLEEPS when idle

            # 4. For each ready FD, schedule its callback
            for key, mask in events:
                callback = key.data  # the coroutine waiting on this FD
                self._ready.append(callback)

            # 5. Check scheduled timers
            now = time.monotonic()
            while self._scheduled and self._scheduled[0].when <= now:
                timer = heapq.heappop(self._scheduled)
                self._ready.append(timer.callback)

            # Go back to step 1
```

This is the entire event loop. Steps 1-5 repeat forever. The "magic" is step 3: one syscall monitors all file descriptors at once.

---

## 7. Layer 6: uvicorn — HTTP Parsing and ASGI Bridge

### How uvicorn creates the server

When you run `cd backend && uv run uvicorn src.main:app --reload`:

```
Shell
 └─ uv run uvicorn src.main:app --reload
     │
     ├─ 1. uvicorn.main() starts
     │     └─ Creates Config object (host, port, workers, reload)
     │
     ├─ 2. uvicorn.Server.startup()
     │     ├─ Creates socket: socket(AF_INET, SOCK_STREAM)
     │     ├─ Binds: bind(("0.0.0.0", 8000))
     │     ├─ Listens: listen(128)
     │     └─ Registers with event loop: loop.create_server(...)
     │
     ├─ 3. Imports your app: importlib.import_module("src.main").app
     │     └─ Your FastAPI() instance is now loaded
     │
     ├─ 4. Runs ASGI lifespan startup
     │     └─ Calls app({"type": "lifespan"}, receive, send)
     │     └─ Your lifespan() context manager runs until yield
     │
     └─ 5. Enters main serve loop
           └─ Event loop runs forever, handling connections
```

### Accepting a new connection

When a client connects:

```
kevent() returns: "server socket (fd=5) is readable"
        │
        ▼
Event loop calls accept(fd=5)          # Kernel syscall
        │
        ├─ Kernel removes one connection from the accept queue
        ├─ Creates a NEW socket for this connection
        ├─ Returns: new_fd=8, client_addr=("10.0.1.5", 52341)
        │
        ▼
uvicorn creates HttpToolsProtocol(new_fd=8)
        │
        ├─ Registers fd=8 with kqueue for READ events
        ├─ Creates httptools.HttpRequestParser()  ← C extension, very fast
        └─ Waits for data on fd=8
```

### Parsing HTTP — httptools (C extension)

uvicorn uses `httptools`, a Python binding for `llhttp` (the same HTTP parser that Node.js uses, written in C). This is important because HTTP parsing is CPU work, and C is ~50-100x faster than pure Python for byte manipulation.

```
Raw bytes from socket                httptools (C parser)         Parsed result
─────────────────────                ───────────────────          ─────────────

b"POST /api/patients/1/              on_url() callback    →     method: "POST"
briefing HTTP/1.1\r\n"                                          url: "/api/patients/1/briefing"
                                                                 http_version: "1.1"

b"Host: localhost:8000\r\n"          on_header() callback →     ("Host", "localhost:8000")

b"Content-Type: application/         on_header() callback →     ("Content-Type",
json\r\n"                                                        "application/json")

b"Content-Length: 42\r\n"            on_header() callback →     ("Content-Length", "42")

b"\r\n"                              on_headers_complete() →    All headers received

b"{\"notes\":\"patient has           on_body() callback   →     body bytes accumulated
diabetes\"}"

(no more data)                       on_message_complete() →    Full HTTP message ready
```

**How fast is this?** Parsing a typical HTTP request with httptools takes **~5-20 microseconds** — roughly the same time as a single Python function call. The C code processes bytes without any Python object allocation overhead.

### Building the ASGI scope

After parsing, uvicorn constructs the ASGI `scope` — a Python dict that describes the request:

```python
# What uvicorn builds (from httptools parse results):
scope = {
    "type": "http",
    "asgi": {"version": "3.0", "spec_version": "2.3"},
    "http_version": "1.1",
    "method": "POST",
    "path": "/api/patients/1/briefing",
    "raw_path": b"/api/patients/1/briefing",
    "query_string": b"",
    "root_path": "",
    "headers": [
        (b"host", b"localhost:8000"),
        (b"content-type", b"application/json"),
        (b"content-length", b"42"),
    ],
    "server": ("0.0.0.0", 8000),
    "client": ("10.0.1.5", 52341),
}
```

Then uvicorn calls your FastAPI app:

```python
await app(scope, receive, send)
```

Where `receive` and `send` are async callables that bridge ASGI messages to the socket:

```python
# receive() — called by FastAPI to get the request body
async def receive():
    # Internally: reads from socket receive buffer via sock_recv()
    return {"type": "http.request", "body": b'{"notes":"patient has diabetes"}'}

# send() — called by FastAPI to write the response
async def send(message):
    if message["type"] == "http.response.start":
        # Buffer status code + headers, don't send yet
        ...
    elif message["type"] == "http.response.body":
        # Combine headers + body, write to socket via sock_sendall()
        # Kernel copies to send buffer → TCP segments → NIC → wire
        ...
```

---

## 8. Layer 7: Starlette and FastAPI

### Starlette: routing and middleware

FastAPI is built on Starlette. When `app(scope, receive, send)` is called:

```
app(scope, receive, send)
│
├─ Starlette ServerErrorMiddleware
│   └─ Catches uncaught exceptions, returns 500
│
├─ CORSMiddleware (added in main.py)
│   └─ Checks Origin header, adds CORS response headers
│
├─ Starlette Router
│   ├─ Iterates registered routes
│   ├─ Tries to match path: "/api/patients/1/briefing"
│   │
│   │  Route trie (simplified):
│   │  /api
│   │   └─ /patients
│   │       └─ /{patient_id:int}
│   │           ├─ GET  → get_patient()
│   │           └─ /briefing
│   │               └─ POST → create_briefing()  ← MATCH
│   │
│   ├─ Extracts path params: patient_id = 1
│   └─ Calls route endpoint handler
│
└─ FastAPI endpoint handler
    ├─ Resolves dependencies (see below)
    ├─ Validates request body (Pydantic)
    ├─ Calls your async def create_briefing()
    ├─ Serializes response (Pydantic → JSON)
    └─ Calls send() with response bytes
```

### FastAPI: dependency resolution

Before your endpoint runs, FastAPI resolves all `Depends()` parameters:

```
Depends(get_session) resolution:
│
├─ FastAPI checks dependency cache (per-request)
│   └─ Not cached yet → need to create
│
├─ Calls get_session() → returns async generator
│   └─ async with async_session() as session:
│       ├─ async_session() checks connection pool
│       │   ├─ Pool has free connection → check out immediately
│       │   └─ Pool exhausted → await until one is returned
│       ├─ Creates AsyncSession wrapping the connection
│       └─ yield session  ← FastAPI receives the session here
│
├─ Injects session into endpoint function signature
│
├─ ─── endpoint runs ───
│
├─ After endpoint returns (or raises):
│   └─ FastAPI resumes generator past yield
│       └─ async with __aexit__:
│           ├─ session.close()
│           └─ Returns connection to pool
```

### Response serialization

After your endpoint returns a `BriefingResponse`:

```
BriefingResponse(flags=[...], summary=..., ...)
│
├─ FastAPI detects response_model (Pydantic BaseModel)
│
├─ Calls .model_dump(mode="json")
│   └─ Pydantic v2 converts Python objects to JSON-compatible types
│       ├─ datetime → "2026-02-28T14:30:00Z" (ISO string)
│       ├─ Enum → string value
│       └─ Nested models → dicts
│
├─ json.dumps(data).encode("utf-8")
│   └─ Python dict → JSON bytes: b'{"flags":[...],...}'
│
├─ FastAPI calls send({"type": "http.response.start", "status": 200,
│   "headers": [(b"content-type", b"application/json")]})
│
└─ FastAPI calls send({"type": "http.response.body",
    "body": b'{"flags":[...],...}'})
    │
    └─ uvicorn: sock_sendall(fd=8, response_bytes)
        │
        └─ Kernel: copies to send buffer → TCP segments → NIC → wire → client
```

---

## 9. Layer 8: Your Application Code

This is where the AI Doctor business logic runs. Covered in detail by doc 03 (FastAPI patterns), doc 04 (RAG async patterns), and doc 05 (SDK internals). The key point for this document is **where your code sits in the stack**:

```
Your code is here:
│
├─ await get_patient_by_id(session, patient_id)
│   │
│   │  Your code calls SQLAlchemy → asyncpg → kernel socket → PostgreSQL
│   │  Suspends at await → event loop runs kevent() → FD becomes readable
│   │  → asyncpg reads response → SQLAlchemy wraps in ORM object → your code resumes
│   │
│   └─ Every "await" is a round-trip through layers 5→4→3→2→1→2→3→4→5
│
├─ await generate_briefing(patient)
│   │
│   │  Your code calls Agent SDK → spawns CLI subprocess → SDK monitors stdout
│   │  Each tool call: stdout→SDK→MCP tool (Qdrant search)→stdin (see doc 05)
│   │  Suspends at each await → event loop handles other requests
│   │
│   └─ Agent turns take seconds, but the event loop is FREE during each wait
│
└─ return BriefingResponse(...)
    │
    └─ FastAPI serializes → uvicorn writes to socket → kernel → NIC → wire → client
```

```
AI DOCTOR EXAMPLE:
A single briefing request for a patient with diabetes + hypertension does
roughly this across all layers:

1. ~4000 voltage transitions on wire (500 bytes HTTP request)
2. NIC DMA writes frame to ring buffer, raises IRQ
3. Kernel TCP stack: reassemble, buffer, wake event loop
4. kevent() returns, event loop runs recv() callback
5. httptools parses HTTP in ~10 microseconds (C code)
6. Starlette routes, FastAPI resolves Depends(get_session)
7. asyncpg sends SQL to PostgreSQL (another full Layer 1-5 round-trip)
8. Agent SDK spawns CLI, streams patient data, agent reasons
9. Agent calls search tool 2-3 times (each: embed→Qdrant→return, full stack)
10. Agent generates briefing, SDK yields ResultMessage
11. Pydantic validates + serializes to JSON
12. uvicorn writes to socket, kernel sends TCP segments
13. NIC transmits ~2000 bytes as electrical signals back to client
```

---

## 10. Complete Round-Trip: All 8 Layers

Here is one HTTP request, from client browser to your endpoint and back, with every layer visible:

```
═══════════════════════════════════════════════════════════════════════
                          REQUEST PATH (client → server)
═══════════════════════════════════════════════════════════════════════

CLIENT BROWSER
  │  JavaScript: fetch("http://localhost:8000/api/patients/1/briefing",
  │    {method: "POST", headers: {...}, body: JSON.stringify(data)})
  │
  │  Browser serializes HTTP request to bytes
  │  OS socket layer segments into TCP, wraps in IP, wraps in Ethernet
  │
  ▼
LAYER 1: WIRE
  │  Electrical signals (voltage transitions) on copper
  │  OR memory copy via loopback (localhost)
  │  Propagation time: ~0.000005ms (localhost) to ~50ms (cross-continent)
  │
  ▼
LAYER 2: NIC
  │  Receives signal → demodulates → verifies CRC
  │  DMA writes Ethernet frame to ring buffer in RAM
  │  Raises hardware interrupt (IRQ)
  │  Time: ~0.001ms
  │
  ▼
LAYER 3: KERNEL TCP/IP
  │  Interrupt handler: strip Ethernet → IP → TCP
  │  TCP state machine: check sequence number, buffer data
  │  Append HTTP bytes to socket receive buffer
  │  Send ACK back to client (may be batched)
  │  Time: ~0.01ms
  │
  ▼
LAYER 4: KERNEL I/O MUX
  │  Mark socket fd as "readable" in kqueue/epoll
  │  Wake up sleeping Python process (event loop was in kevent())
  │  Time: ~0.005ms
  │
  ▼
LAYER 5: PYTHON EVENT LOOP
  │  kevent() returns: [{fd=8, filter=READ}]
  │  Event loop: schedule read callback for fd=8
  │  Callback: sock_recv(fd=8, 65536) → raw HTTP bytes
  │  Time: ~0.01ms
  │
  ▼
LAYER 6: UVICORN
  │  httptools (C) parses HTTP request → scope dict
  │  Creates receive/send ASGI callables
  │  Calls: await app(scope, receive, send)
  │  Time: ~0.02ms
  │
  ▼
LAYER 7: STARLETTE + FASTAPI
  │  Middleware chain (CORS, errors)
  │  Router matches: /api/patients/{patient_id}/briefing → POST
  │  FastAPI resolves Depends(get_session) → async DB session
  │  Validates path params: patient_id=1
  │  Calls: await create_briefing(patient_id=1, session=...)
  │  Time: ~0.05ms
  │
  ▼
LAYER 8: YOUR CODE
  │  await get_patient_by_id(session, 1)     → ~5ms (Postgres round-trip)
  │  await generate_briefing(patient)        → ~8000ms (Claude agent turns)
  │    └── agent searches guidelines 2-3x   → ~500ms each (Qdrant round-trips)
  │  return BriefingResponse(...)
  │  Time: ~8500ms (but CPU active for only ~0.2ms of this)

═══════════════════════════════════════════════════════════════════════
                          RESPONSE PATH (server → client)
═══════════════════════════════════════════════════════════════════════

LAYER 8 → 7: YOUR CODE → FASTAPI
  │  BriefingResponse → model_dump() → json.dumps() → bytes
  │  Time: ~0.1ms
  │
  ▼
LAYER 6: UVICORN
  │  send({"type": "http.response.start", "status": 200, ...})
  │  send({"type": "http.response.body", "body": b'{"flags":[...]}'})
  │  sock_sendall(fd=8, full_response_bytes)
  │  Time: ~0.01ms
  │
  ▼
LAYER 5: PYTHON
  │  send() syscall: copies bytes to kernel send buffer
  │  Non-blocking: returns immediately after copy
  │  Time: ~0.005ms
  │
  ▼
LAYER 4 → 3: KERNEL
  │  TCP layer segments response into ~1460-byte chunks (MSS)
  │  Wraps each in TCP header (seq, ack, window) → IP header → Ethernet
  │  Queues frames for NIC transmission
  │  Time: ~0.01ms
  │
  ▼
LAYER 2: NIC
  │  DMA reads frame from kernel's TX ring buffer
  │  Serializes to electrical signals
  │  Time: ~0.001ms
  │
  ▼
LAYER 1: WIRE
  │  Electrical signals propagate to client NIC
  │
  ▼
CLIENT BROWSER
  │  NIC → kernel → browser's socket → JavaScript fetch() resolves
  │  Browser parses JSON, updates React state, re-renders UI
```

---

## 11. Where Time Is Actually Spent

For a typical AI Doctor briefing request (~8.5 seconds end-to-end):

```
Layer    Component                 Time          Type     Notes
─────    ─────────                 ────          ────     ─────
1        Wire (localhost)          0.000005ms    latency  Memory copy, no real wire
2        NIC + DMA + IRQ          0.001ms       CPU      Hardware interrupt handler
3        Kernel TCP/IP            0.01ms        CPU      Reassembly, buffering, ACK
4        kqueue wakeup            0.005ms       CPU      Process scheduling
5        Event loop + recv()      0.01ms        CPU      Python callback dispatch
6        httptools parse          0.02ms        CPU      C extension, very fast
7        Starlette + FastAPI      0.05ms        CPU      Routing, DI, validation
8a       DB query (Postgres)      5ms           I/O      Round-trip to database
8b       Agent SDK (Claude)       8000ms        I/O      Multi-turn agent reasoning
8c       Qdrant searches (2-3x)   500ms         I/O      Embed + vector search each
7        JSON serialization       0.1ms         CPU      Pydantic + json.dumps
6-1      Response send            0.05ms        CPU      All layers back to client
                                  ────────
         TOTAL                    ~8505ms

         Total CPU work:          ~0.25ms  (0.003% of total time)
         Total I/O waiting:       ~8505ms  (99.997% of total time)
```

**This is why async works so well for this app.** During 99.997% of request time, the coroutine is suspended and the CPU is free. One event loop thread handles hundreds of concurrent briefing requests because they're all waiting on network I/O, not consuming CPU.

```
1 uvicorn worker handling 100 concurrent briefing requests:

CPU utilization: 100 × 0.25ms = 25ms of CPU work (spread over 8.5 seconds)
                 = 0.3% CPU usage

Memory: 100 × ~2KB per coroutine = ~200KB
        + event loop overhead     = ~1MB total

Compare with thread-per-request:
Memory: 100 × ~8MB per thread stack = ~800MB
CPU: same actual work, but constant context switching overhead
```

---

## 12. What File Descriptors Actually Are

File descriptors appear everywhere in this document. Here's what they actually are at the kernel level:

```
                    Process (your Python uvicorn server)
                   ┌──────────────────────────────────────┐
                   │                                      │
                   │  File Descriptor Table               │
                   │  (per-process, array of pointers)    │
                   │                                      │
                   │  Index │ Pointer                     │
                   │  ──────┼──────────────────────       │
                   │  0     │ → stdin (terminal)          │
                   │  1     │ → stdout (terminal)         │
                   │  2     │ → stderr (terminal)         │
                   │  3     │ → /dev/null                 │
                   │  4     │ → kqueue instance           │
                   │  5     │ → server socket (LISTEN) ───┼──→ Kernel socket struct
                   │  6     │ → PostgreSQL connection ────┼──→ Kernel socket struct
                   │  7     │ → (closed)                  │
                   │  8     │ → client connection #1  ────┼──→ Kernel socket struct
                   │  9     │ → client connection #2  ────┼──→ Kernel socket struct
                   │  10    │ → Qdrant connection     ────┼──→ Kernel socket struct
                   │  ...   │                             │
                   └──────────────────────────────────────┘
```

A file descriptor is simply an **integer index** into a per-process table. The kernel maintains the table. Each entry points to a kernel object (socket, file, pipe, device, etc.).

When Python calls `socket.socket()`, the kernel:
1. Creates an internal socket structure
2. Finds the lowest available index in the FD table
3. Points that index at the new socket structure
4. Returns the integer to Python

When Python calls `recv(fd=8, 65536)`, the kernel:
1. Looks up index 8 in the process's FD table
2. Follows the pointer to the socket structure
3. Copies data from the socket's receive buffer to Python's memory
4. Returns the byte count

**Why integers?** Efficiency. Passing a small integer through a syscall is much faster than passing a pointer or string. The kernel validates the index and does the lookup internally.

---

## 13. uvloop vs asyncio: Why uvicorn Prefers uvloop

uvicorn uses `uvloop` by default on macOS/Linux. uvloop is a drop-in replacement for `asyncio`'s event loop, but faster:

```
                asyncio (pure Python + C)          uvloop (Cython + libuv/C)
                ─────────────────────────          ──────────────────────────

Architecture:   Python event loop class            Cython wrapper around libuv
                Uses selectors module              libuv is the C library that
                (Python wrapper for kqueue/epoll)  powers Node.js

Socket I/O:     Python → selectors → syscall       Cython → libuv → syscall
                ~3 Python function calls            ~0 Python function calls
                per I/O operation                   (stays in C/Cython)

Performance:    Baseline                           2-4x faster for I/O-heavy
                                                   workloads (benchmarks vary)

Callback        Python deque + heapq               C-level data structures
scheduling:     (good, but Python overhead)        (no Python object overhead)

Timer           Python heapq (O(log n))            libuv's C timer heap
resolution:     ~1ms granularity                   ~1ms granularity, less overhead
```

The key difference: uvloop minimizes the number of **Python-level operations** per I/O event. In asyncio, each `kevent()` return involves Python callback lookup, deque operations, and function calls. In uvloop, this stays in C/Cython until the actual coroutine resumption.

For the AI Doctor, this means faster request dispatch and lower overhead per connection — but the actual request time is dominated by Claude API latency (~8 seconds), so the 2-4x event loop speedup applies to the ~0.25ms of overhead, not the 8.5 seconds of I/O wait.

---

## 14. TCP Flow Control and Congestion Control

Two mechanisms the kernel uses to manage data rates — invisible to your Python code but critical to understanding network I/O:

### Flow control (receiver-side)

Flow control prevents the sender from overwhelming the receiver's buffer:

```
Client (sender)                              Server (receiver)
───────────────                              ─────────────────

Sends 10KB of data ──────────────────────→   Receive buffer: [10KB/256KB free]
                                             Sends ACK with window=246KB
                    ←────────────────────
"I have 246KB of buffer space left"

Sends 200KB ─────────────────────────────→   Receive buffer: [210KB/256KB]
                                             Python hasn't called recv() yet!
                                             Sends ACK with window=46KB
                    ←────────────────────
"Slow down, only 46KB left"

                                             Python calls recv(), reads 210KB
                                             Receive buffer: [0KB/256KB]
                                             Sends ACK with window=256KB
                    ←────────────────────
"Buffer empty, send freely"
```

**Why this matters for async servers:** If your Python code is slow to `recv()` (because the event loop is busy with CPU work), the receive buffer fills up, the window shrinks, and the client automatically slows down. This is back-pressure propagating through TCP — and it's why blocking the event loop is so dangerous: it creates back-pressure on ALL connections.

### Congestion control (network-side)

Congestion control prevents the sender from overwhelming the network:

```
Connection starts:
  cwnd (congestion window) = 10 segments (~14KB)  ← "slow start"

Each ACK received:
  cwnd doubles (exponential growth)               ← "slow start phase"
  10 → 20 → 40 → 80 → 160 segments

Packet loss detected (timeout or 3 dup ACKs):
  ssthresh = cwnd / 2                             ← "congestion detected!"
  cwnd = 1 (timeout) or cwnd/2 (fast recovery)    ← "back off"

After recovery:
  cwnd grows linearly (+1 per RTT)                ← "congestion avoidance"
```

This is entirely kernel-managed. Your Python code never sees it. But it explains why:
- First requests on a new TCP connection are slower (small initial window)
- Keep-alive connections are faster (window has already grown)
- Network congestion slows ALL your outbound API calls (to Claude, Qdrant, Postgres)

---

## 15. The Accept Queue: SYN Queue and Completed Queue

When you call `listen(128)`, the kernel creates two queues for handling incoming connections:

```
Client                          Kernel (for your server socket)
──────                          ────────────────────────────────

SYN ────────────────────→      SYN QUEUE (half-open connections)
                                ┌─────────────────────────────┐
                                │ {client: 10.0.1.5:52341,    │
                    ←── SYN-ACK │  state: SYN_RECEIVED,       │
                                │  timestamp: ...}            │
ACK ────────────────────→      │                              │
                                └─────────┬───────────────────┘
                                          │ 3-way handshake complete
                                          ▼
                                ACCEPT QUEUE (completed connections)
                                ┌─────────────────────────────┐
                                │ {client: 10.0.1.5:52341,    │
                                │  state: ESTABLISHED,        │
                                │  new_socket_fd: 8}          │
                                │                             │
                                │ {client: 10.0.1.6:41122,    │
                                │  state: ESTABLISHED,        │
                                │  new_socket_fd: 9}          │
                                └─────────┬───────────────────┘
                                          │ Python calls accept()
                                          ▼
                                Event loop: new_fd=8, new_fd=9
                                Create protocol handler for each
```

The `128` in `listen(128)` is the **backlog** — the maximum size of the accept queue. If 129 connections complete the handshake before Python calls `accept()`, the kernel drops the 129th SYN.

**Why this matters:** If your event loop is blocked (CPU-heavy work, accidental `time.sleep()`), it can't call `accept()`. The accept queue fills up. New connections get dropped. Users see "connection refused" errors. This is another reason why keeping the event loop fast is critical.

---

## 16. Keep-Alive Connections

HTTP/1.1 uses keep-alive by default — the TCP connection stays open for multiple requests:

```
WITHOUT keep-alive (HTTP/1.0 default):

Request 1:  [TCP handshake 1.5ms][HTTP request/response][TCP close]
Request 2:  [TCP handshake 1.5ms][HTTP request/response][TCP close]
Request 3:  [TCP handshake 1.5ms][HTTP request/response][TCP close]

Total overhead: 3 × handshake + 3 × close = ~9ms of pure overhead


WITH keep-alive (HTTP/1.1 default):

            [TCP handshake 1.5ms]
Request 1:  [HTTP request/response]
Request 2:  [HTTP request/response]
Request 3:  [HTTP request/response]
            [TCP close]

Total overhead: 1 × handshake + 1 × close = ~3ms of pure overhead
```

uvicorn manages keep-alive at the protocol level:

```
Connection established (fd=8)
│
├─ Request 1: parse HTTP → call app() → send response
│   └─ Check: Connection: keep-alive header? Yes → keep fd=8 open
│
├─ Request 2: parse HTTP → call app() → send response
│   └─ Check: keep-alive? Yes → keep open
│
├─ Request 3: parse HTTP → call app() → send response
│   └─ Check: Connection: close? → close fd=8
│
└─ OR: keep-alive timeout expires (default 5s) → close fd=8
```

**Why this matters for the AI Doctor frontend:** The React frontend makes multiple API calls (load patient, generate briefing, etc.). With keep-alive, all requests reuse the same TCP connection, avoiding repeated handshake overhead and benefiting from an already-grown TCP congestion window.

Each keep-alive connection holds a file descriptor open. uvicorn's keep-alive timeout (default 5 seconds) ensures idle connections are eventually closed so file descriptors are reclaimed.

---

## 17. Summary

### The 8-layer stack at a glance

| Layer | Component | What It Does | Time |
|-------|-----------|-------------|------|
| 1 | Wire/Radio | Propagates electrical/optical/radio signals | ~0.000005ms (local) |
| 2 | NIC | DMA write to RAM, hardware interrupt | ~0.001ms |
| 3 | Kernel TCP/IP | Reassembly, buffering, ACK generation | ~0.01ms |
| 4 | Kernel I/O Mux | kqueue/epoll wakes sleeping process | ~0.005ms |
| 5 | Python Event Loop | Callback dispatch, coroutine scheduling | ~0.01ms |
| 6 | uvicorn | httptools HTTP parse, ASGI bridge | ~0.02ms |
| 7 | Starlette/FastAPI | Routing, DI, validation, serialization | ~0.05ms |
| 8 | Your Code | Business logic, DB queries, agent calls | ~8500ms |

### Key insights

1. **The CPU barely works during a request.** For an 8.5-second briefing request, the CPU does ~0.25ms of work (0.003%). The rest is I/O waiting — and that's why async handles hundreds of concurrent requests on one thread.

2. **Data crosses the user/kernel boundary twice per I/O operation.** Python calls `recv()` → syscall → kernel copies data → returns to Python. This boundary crossing costs ~1 microsecond each way. Minimizing syscalls is why buffering exists at every layer.

3. **The NIC bypasses the CPU for data transfer.** DMA lets the NIC write directly to RAM. The CPU only gets involved via the interrupt handler, which runs for microseconds. On busy servers, interrupt coalescing (NAPI) batches many frames into one interrupt.

4. **kqueue/epoll is the foundation of everything.** The entire async Python ecosystem — asyncio, uvloop, uvicorn, FastAPI — ultimately rests on one kernel syscall that monitors file descriptors. Understanding this one call explains why async works.

5. **TCP does the heavy lifting invisibly.** Reassembly, retransmission, flow control, congestion control — all handled by the kernel. Your Python code just reads an ordered byte stream.

6. **Keep-alive connections and connection pooling** (asyncpg pool, Qdrant client pool) amortize TCP handshake costs across many requests. This is why the first request is slower than subsequent ones.

### Cross-references

- **`01-SYNC-VS-ASYNC.md`** — Why async exists (the blocking problem, I/O-bound vs CPU-bound)
- **`02-EVENT-LOOP-AND-COROUTINES.md`** — Python-level event loop mechanics (coroutines, await, gather)
- **`03-FASTAPI-ASYNC-ARCHITECTURE.md`** — FastAPI/Starlette/uvicorn at the application level
- **`04-ASYNC-PATTERNS-FOR-RAG.md`** — Async patterns for the RAG pipeline
- **`05-SDK-STREAMING-AND-MCP-INTERNALS.md`** — SDK subprocess protocol and MCP tool bridge

---

**Previous**: `05-SDK-STREAMING-AND-MCP-INTERNALS.md` — SDK streaming and MCP internals
