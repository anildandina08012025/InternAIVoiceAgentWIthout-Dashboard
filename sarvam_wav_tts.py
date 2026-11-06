"""Decode Sarvam's WAV responses with the matching LiveKit audio decoder."""
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins.sarvam import tts as sarvam_tts


class _WavEmitter:
    def __init__(self, emitter):
        self._emitter = emitter

    def initialize(self, **kwargs):
        kwargs['mime_type'] = 'audio/wav'
        return self._emitter.initialize(**kwargs)

    def __getattr__(self, name):
        return getattr(self._emitter, name)


class _WavChunkedStream(sarvam_tts.ChunkedStream):
    async def _run(self, output_emitter):
        await super()._run(_WavEmitter(output_emitter))


class SarvamWavTTS(sarvam_tts.TTS):
    def synthesize(self, text, *, conn_options=None):
        return _WavChunkedStream(tts=self, input_text=text, conn_options=conn_options or DEFAULT_API_CONNECT_OPTIONS)

