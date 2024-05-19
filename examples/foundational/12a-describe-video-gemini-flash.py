#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import aiohttp
import os
import sys

from pipecat.frames.frames import Frame, TextFrame, UserImageRequestFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.user_response import UserResponseAggregator
from pipecat.processors.aggregators.vision_image_frame import VisionImageFrameAggregator
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.google import GoogleLLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.vad.silero import SileroVAD

from runner import configure

from loguru import logger

from dotenv import load_dotenv
load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class UserImageRequester(FrameProcessor):

    def __init__(self, participant_id: str | None = None):
        super().__init__()
        self._participant_id = participant_id

    def set_participant_id(self, participant_id: str):
        self._participant_id = participant_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if self._participant_id and isinstance(frame, TextFrame):
            await self.push_frame(UserImageRequestFrame(self._participant_id), FrameDirection.UPSTREAM)
        await self.push_frame(frame, direction)


async def main(room_url: str, token):
    async with aiohttp.ClientSession() as session:
        transport = DailyTransport(
            room_url,
            token,
            "Describe participant video",
            DailyParams(
                audio_in_enabled=True,  # This is so Silero VAD can get audio data
                audio_out_enabled=True,
                transcription_enabled=True
            )
        )

        vad = SileroVAD()

        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        )

        user_response = UserResponseAggregator()

        image_requester = UserImageRequester()

        vision_aggregator = VisionImageFrameAggregator()

        google = GoogleLLMService(model="gemini-1.5-flash-latest")

        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            await tts.say("Hi there! Feel free to ask me what I see.")
            transport.capture_participant_video(participant["id"], framerate=0)
            transport.capture_participant_transcription(participant["id"])
            image_requester.set_participant_id(participant["id"])

        pipeline = Pipeline([transport.input(), vad, user_response, image_requester,
                             vision_aggregator, google, tts, transport.output()])

        task = PipelineTask(pipeline)

        runner = PipelineRunner()

        await runner.run(task)

if __name__ == "__main__":
    (url, token) = configure()
    asyncio.run(main(url, token))