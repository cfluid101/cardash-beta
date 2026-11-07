// SPDX-License-Identifier: GPL-3.0-only
// PCM playback uses standard Web Audio nodes, including on HTTP hotspot pages.
// Call enable() directly from a click/touch handler, before awaiting network work.
(() => {
  'use strict';
  const MAX_PAYLOAD = 12 + 65536, MAX_AHEAD = .5, LEAD = .12;
  const lanes = new Map();
  let context, master, analyser, desiredSession = null, connection = null;
  let enabled = false, muted = false;
  const counters = {
    receivedFrames: 0, sampleFrames: 0, nonzeroSamples: 0, peak: 0,
    scheduledFrames: 0, droppedFrames: 0, sequenceGaps: 0,
    underruns: 0, resets: 0, connections: 0, parserBytes: 0,
    connectionState: 'idle', error: ''
  };

  function setGain(param, value) {
    param.setTargetAtTime(value, context.currentTime, .015);
  }
  function clearLane(lane, count = true) {
    for (const entry of lane.sources) {
      entry.source.onended = null;
      try { entry.source.stop(); } catch (_) {}
      entry.source.disconnect();
    }
    lane.sources.clear();
    lane.next = 0;
    if (count) counters.resets++;
  }
  function clearSources() {
    for (const lane of lanes.values()) {
      clearLane(lane, false);
      lane.gain.disconnect();
    }
    lanes.clear();
  }
  function stop() {
    desiredSession = null;
    const old = connection;
    connection = null;
    if (old) old.abort.abort();
    clearSources();
    counters.parserBytes = 0;
    counters.connectionState = 'idle';
  }
  function resetCounters() {
    for (const name of Object.keys(counters)) {
      if (typeof counters[name] === 'number') counters[name] = 0;
    }
    counters.error = '';
  }
  function laneFor(id) {
    let lane = lanes.get(id);
    if (!lane) {
      const gain = context.createGain();
      gain.connect(master);
      lane = { gain, sources: new Set(), next: 0, rate: 0, channels: 0, sequence: null, ducked: false, media: false, gainValue: 1 };
      lanes.set(id, lane);
    }
    return lane;
  }

  function receive(payload) {
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    const rate = view.getUint32(0), channels = view.getUint8(4), id = view.getUint8(5);
    const flags = view.getUint16(6), sequence = view.getUint32(8);
    const pcmBytes = payload.length - 12;
    if (rate < 8000 || rate > 48000 || (channels !== 1 && channels !== 2) || id > 7 ||
        flags & ~7 || pcmBytes % (2 * channels)) throw new Error('Invalid native audio format');
    const frames = pcmBytes / (2 * channels), duration = frames / rate;
    if (duration > MAX_AHEAD) throw new Error('Native audio packet exceeds playback budget');
    counters.receivedFrames++;
    counters.sampleFrames += frames;
    // Count real decoded PCM independently of whether browser playback is enabled.
    for (let at = 12; at < payload.length; at += 2) {
      const value = view.getInt16(at, true);
      if (value) counters.nonzeroSamples++;
      counters.peak = Math.max(counters.peak, Math.abs(value / 32768));
    }
    if (!enabled || context.state !== 'running') {
      counters.droppedFrames++;
      clearSources();
      return;
    }
    const lane = laneFor(id), reset = Boolean(flags & 1);
    if (reset || lane.rate !== rate || lane.channels !== channels) {
      clearLane(lane);
      lane.sequence = null;
    }
    lane.rate = rate; lane.channels = channels;
    if (lane.sequence !== null) {
      const delta = (sequence - lane.sequence) >>> 0;
      if (!delta || delta > 0x7fffffff) { counters.droppedFrames++; return; }
      if (delta > 1) {
        counters.sequenceGaps += delta - 1;
        clearLane(lane);
      }
    }
    lane.sequence = sequence;
    lane.media = Boolean(flags & 2);
    lane.ducked = lane.media && Boolean(flags & 4);
    const gainValue = lane.ducked ? .25 : 1;
    if (lane.gainValue !== gainValue) {
      setGain(lane.gain.gain, gainValue);
      lane.gainValue = gainValue;
    }
    if (!frames) return;

    const now = context.currentTime;
    for (const entry of lane.sources) {
      if (entry.end <= now) {
        entry.source.onended = null;
        entry.source.disconnect();
        lane.sources.delete(entry);
      }
    }
    if (lane.next && lane.next < now - .01) counters.underruns++;
    const base = now + Math.min(LEAD, MAX_AHEAD - duration);
    let start = lane.next > now ? lane.next : base;
    // A slow browser cannot accumulate seconds of old music or unbounded nodes.
    if (start + duration > now + MAX_AHEAD || lane.sources.size >= 64) {
      clearLane(lane);
      counters.droppedFrames++;
      start = base;
    }
    const buffer = context.createBuffer(channels, frames, rate);
    for (let channel = 0; channel < channels; channel++) {
      const output = buffer.getChannelData(channel);
      for (let frame = 0; frame < frames; frame++) {
        output[frame] = view.getInt16(12 + 2 * (frame * channels + channel), true) / 32768;
      }
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(lane.gain);
    const entry = { source, end: start + duration };
    lane.sources.add(entry);
    source.onended = () => { lane.sources.delete(entry); source.disconnect(); };
    source.start(start);
    lane.next = entry.end;
    counters.scheduledFrames += frames;
  }

  // Only one bounded frame is retained; arbitrarily fragmented/coalesced HTTP
  // reads never cause an accumulating concatenation buffer.
  function parser(consume) {
    const header = new Uint8Array(4);
    let headAt = 0, payload = null, at = 0;
    return {
      push(chunk) {
        let offset = 0;
        while (offset < chunk.length) {
          if (!payload) {
            const n = Math.min(4 - headAt, chunk.length - offset);
            header.set(chunk.subarray(offset, offset + n), headAt);
            offset += n; headAt += n;
            counters.parserBytes = headAt;
            if (headAt < 4) continue;
            const length = new DataView(header.buffer).getUint32(0);
            if (length < 12 || length > MAX_PAYLOAD) throw new Error('Invalid native audio frame length');
            payload = new Uint8Array(length); at = 0;
          }
          const n = Math.min(payload.length - at, chunk.length - offset);
          payload.set(chunk.subarray(offset, offset + n), at);
          offset += n; at += n;
          counters.parserBytes = 4 + at;
          if (at === payload.length) {
            consume(payload);
            payload = null; at = 0; headAt = 0;
            counters.parserBytes = 0;
          }
        }
      },
      finish() { if (payload || headAt) throw new Error('Truncated native audio frame'); }
    };
  }

  async function enable() {
    // Construction and resume happen synchronously in the caller's user gesture.
    if (!context) {
      const Constructor = window.AudioContext || window.webkitAudioContext;
      if (!Constructor) throw new Error('This browser does not support CarDash audio');
      context = new Constructor({ latencyHint: 'interactive' });
      master = context.createGain(); master.gain.value = muted ? 0 : .6;
      analyser = context.createAnalyser(); analyser.fftSize = 256;
      master.connect(analyser); analyser.connect(context.destination);
    }
    const resumed = context.resume();
    try {
      await resumed;
      if (context.state !== 'running') throw new Error('Tap Sound to enable browser audio');
      enabled = true; counters.error = '';
      if (desiredSession && !connection) connect(desiredSession);
      return true;
    } catch (error) {
      enabled = false; counters.error = error.message;
      throw error;
    }
  }

  function connect(session) {
    if (typeof session !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(session)) {
      counters.error = 'Invalid native audio session';
      return Promise.resolve(false);
    }
    if (desiredSession !== session) {
      stop(); resetCounters(); desiredSession = session;
    }
    if (!enabled || !context || context.state !== 'running') {
      counters.connectionState = 'awaiting-gesture';
      return Promise.resolve(false);
    }
    if (connection) return connection.ready;
    let ready;
    const current = { abort: new AbortController(), ready: new Promise(resolve => { ready = resolve; }) };
    connection = current;
    counters.connectionState = 'connecting'; counters.error = '';
    (async () => {
      let reader;
      try {
        const response = await (window.CarDashTransport ? window.CarDashTransport.fetch : fetch)('/audio', {
          signal: current.abort.signal, credentials: 'same-origin', cache: 'no-store',
          headers: { 'X-CarDash-Session': session }
        });
        if (connection !== current) return;
        if (!response.ok || !response.body) throw new Error('Native audio connection failed (' + response.status + ')');
        reader = response.body.getReader();
        const decoder = parser(receive);
        counters.connections++; counters.connectionState = 'connected'; ready(true);
        for (;;) {
          const { value, done } = await reader.read();
          if (connection !== current) break;
          if (done) { decoder.finish(); throw new Error('Native audio stream ended'); }
          decoder.push(value);
        }
      } catch (error) {
        if (connection === current && error.name !== 'AbortError') counters.error = error.message;
      } finally {
        ready(false);
        if (reader) { try { await reader.cancel(); } catch (_) {} }
        if (connection === current) {
          connection = null; clearSources(); counters.parserBytes = 0;
          counters.connectionState = counters.error ? 'disconnected' : 'idle';
        }
      }
    })();
    return current.ready;
  }

  function muteToggle() {
    muted = !muted;
    if (master) setGain(master.gain, muted ? 0 : .6);
    return muted;
  }
  function stats() {
    const now = context ? context.currentTime : 0;
    let scheduledAhead = 0, sources = 0, energy = 0;
    for (const lane of lanes.values()) {
      scheduledAhead = Math.max(scheduledAhead, lane.next - now);
      sources += lane.sources.size;
    }
    if (analyser && context.state === 'running') {
      const samples = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(samples);
      for (const value of samples) energy += value * value;
      energy = Math.sqrt(energy / samples.length);
    }
    return {
      ...counters, enabled, muted, contextState: context ? context.state : 'not-created',
      scheduledAhead: Math.max(0, scheduledAhead), sources, lanes: lanes.size,
      // This proves signal in the browser audio graph, not audible speaker output.
      analyserEnergy: energy
    };
  }
  window.CarDashAudio = { enable, connect, stop, muteToggle, get stats() { return stats(); } };
  window.addEventListener('pagehide', stop);
})();
