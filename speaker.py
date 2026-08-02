import time
from pathlib import Path

import pygame


class Speaker:
    """Reusable audio player."""

    def __init__(
        self,
        sound_file: str | Path,
        volume: float = 1.0,
    ) -> None:
        self.sound_file = Path(sound_file).expanduser().resolve()

        if not self.sound_file.is_file():
            raise FileNotFoundError(
                f"Sound file not found: {self.sound_file}"
            )

        if not 0.0 <= volume <= 1.0:
            raise ValueError("Volume must be between 0.0 and 1.0")

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        self.sound = pygame.mixer.Sound(str(self.sound_file))
        self.sound.set_volume(volume)
        self.channel: pygame.mixer.Channel | None = None

    def play(self, repeat: int = 1, blocking: bool = False) -> None:
        """
        Play the sound.

        repeat=1 plays once.
        repeat=3 plays three times.
        blocking=True waits until playback finishes.
        """
        if repeat < 1:
            raise ValueError("repeat must be at least 1")

        # pygame uses loops=0 for one playback.
        self.channel = self.sound.play(loops=repeat - 1)

        if self.channel is None:
            raise RuntimeError("No audio channel was available")

        if blocking:
            while self.channel.get_busy():
                time.sleep(0.05)

    def stop(self) -> None:
        """Immediately stop the barking sound."""
        if self.channel is not None:
            self.channel.stop()

    def is_playing(self) -> bool:
        """Return True while the barking sound is playing."""
        return self.channel is not None and self.channel.get_busy()

    def set_volume(self, volume: float) -> None:
        """Set volume between 0.0 and 1.0."""
        if not 0.0 <= volume <= 1.0:
            raise ValueError("Volume must be between 0.0 and 1.0")

        self.sound.set_volume(volume)

    def close(self) -> None:
        """Release the audio system."""
        self.stop()
        pygame.mixer.quit()