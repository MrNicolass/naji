class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = 1024;
    this.buffer = new Int16Array(this.size);
    this.count = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      let sample = channel[i];
      if (sample > 1) sample = 1;
      if (sample < -1) sample = -1;
      this.buffer[this.count++] = Math.round(sample * 32767);
      if (this.count >= this.size) {
        this.port.postMessage(this.buffer.slice(0));
        this.count = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
