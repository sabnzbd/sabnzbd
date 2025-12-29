## Download flow (Downloader + NewsWrapper)

1. **Job ingestion**  
   - NZBs arrive via UI/API/URL; `urlgrabber.py` fetches remote NZBs, `nzbparser.py` turns them into `NzbObject`s, and `nzbqueue.NzbQueue` stores ordered jobs with priorities and categories.

2. **Queue to articles**  
   - When servers need work, `NzbQueue.get_articles` (called from `Server.get_article` in `downloader.py`) hands out batches of `Article`s per server, respecting retention, priority, and forced/paused items.

3. **Downloader setup**  
   - `Downloader` thread loads server configs (`config.get_servers`), instantiates `Server` objects (per host/port/SSL/threads), and spawns `NewsWrapper` instances per configured connection.  
   - A `selectors.DefaultSelector` watches all sockets; `BPSMeter` tracks throughput and speed limits; timers manage server penalties/restarts.

4. **Connection establishment (NewsWrapper.init_connect → NNTP.connect)**  
   - `Server.request_addrinfo` resolves fastest address; `NewsWrapper` builds an `NNTP` socket, wraps SSL if needed, sets non-blocking, and registers with the selector.  
   - First server greeting (200/201) is queued; `finish_connect` drives the login handshake (`AUTHINFO USER/PASS`) and handles temporary (480) or permanent (400/502) errors.

5. **Request scheduling & pipelining**  
   - `write()` chooses the next article command (`STAT/HEAD` for precheck, `BODY` or `ARTICLE` otherwise).  
   - Concurrency is limited by `server.pipelining_requests`; commands are queued and sent; partial writes are buffered.

6. **Receiving data**  
   - Selector events route to `process_nw_read`; `NewsWrapper.read` pulls bytes (SSL optimized via sabctools), parses NNTP responses, and calls `on_response`.  
   - Successful BODY/ARTICLE (220/222) updates per-server stats; missing/500 variants toggle capability flags (BODY/STAT support).

7. **Decoding and caching**  
   - `Downloader.decode` hands responses to `decoder.decode`, which yEnc/UU decodes, CRC-checks, and stores payloads in `ArticleCache` (memory or disk spill).  
   - Articles with DMCA/bad data trigger retry on other servers until `max_art_tries` is exceeded.

8. **Assembly to files**  
   - `Assembler` worker consumes decoded pieces, writes to the target file, updates CRC, and cleans admin markers. It guards disk space (`diskspace_check`) and schedules direct unpack or PAR2 handling when files finish.

9. **Queue bookkeeping**  
   - `NzbQueue.register_article` records success/failure; completed files advance NZF/NZO state. If all files done, the job moves to post-processing (`PostProcessor.process`), which runs `newsunpack`, scripts, sorting, etc.

10. **Control & resilience**  
    - Pausing/resuming (`Downloader.pause/resume`), bandwidth limiting, and sleep tuning happen in the main loop.  
    - Errors/timeouts lead to `reset_nw` (close socket, return article, maybe penalize server). Optional servers can be temporarily disabled; required ones schedule resumes.  
    - Forced disconnect/shutdown drains sockets, refreshes DNS, and exits cleanly.
