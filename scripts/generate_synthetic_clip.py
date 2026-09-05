"""Generate the synthetic test clip with Veo on Vertex AI (labelled in SYNTHETIC.md).

The clip carries no real brand, no person and no text: the claim overlay and the C2PA manifest are
added afterwards by scripts/make_synthetic_asset.sh so that the text is crisp and the claim exact.
Usage: python scripts/generate_synthetic_clip.py [model]
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

from google import genai
from google.genai import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from airlock import settings  # noqa: E402

OUT = f"gs://{settings.bucket()}/synthetic/"
PROMPT = (
    "Product commercial shot: a single plain unbranded matte white aluminium can of sparkling water on a "
    "light oak table by a window, soft morning light, fine condensation drops, a thin slice of lime beside it, "
    "slow cinematic push-in, shallow depth of field, calm and premium, photorealistic. No people, no hands, "
    "no text, no logos, no labels on the can."
)


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "veo-3.1-generate-001"
    client = genai.Client(vertexai=True, project=settings.project(), location=settings.region())
    t0 = time.time()
    op = client.models.generate_videos(
        model=model,
        prompt=PROMPT,
        config=types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=8,
            aspect_ratio="16:9",
            resolution="1080p",
            person_generation="dont_allow",
            generate_audio=False,
            enhance_prompt=True,
            negative_prompt="people, hands, faces, text, letters, logos, brand names, watermark, glitch, distortion",
            output_gcs_uri=OUT,
        ),
    )
    while not op.done:
        time.sleep(10)
        op = client.operations.get(op)
    if op.error:
        sys.exit(f"veo error: {op.error}")
    if op.response is None:
        sys.exit("veo returned no response and no error")
    vids = op.response.generated_videos or []
    print(json.dumps({"model": model, "elapsed_s": round(time.time() - t0, 1), "videos": [v.video.uri if v.video else None for v in vids],
                      "rai_filtered": getattr(op.response, "rai_media_filtered_count", None),
                      "rai_reasons": getattr(op.response, "rai_media_filtered_reasons", None)}))


if __name__ == "__main__":
    main()
