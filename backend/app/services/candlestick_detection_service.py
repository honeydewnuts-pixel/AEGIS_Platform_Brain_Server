"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : candlestick_detection_service.py

Purpose :
Candlestick Detection Service.

Current Stage:
CP-005 – Batch 1

Responsibilities
----------------
• Accept plotting area from Chart Detection Engine
• Crop the plotting region
• Detect candidate candlestick objects
• Compute basic geometry
• Classify candle colour
• Return structured candidates

NOTE
----
This module deliberately does NOT:
- recognise candlestick patterns
- generate trading signals
====================================================================
"""

from __future__ import annotations

from typing import Any

import cv2

from app.core.logging import configure_logging
from app.services.image_processing_service import ImageProcessingService


class CandlestickDetectionService:
    """
    Detect candidate candlesticks within the plotting area.
    """

    def __init__(self) -> None:

        self.logger = configure_logging()
        self.image_service = ImageProcessingService()

    def detect(
        self,
        image_path: str,
        plotting_area: dict[str, int],
    ) -> dict[str, Any]:
        """
        Detect candlestick candidates.

        Parameters
        ----------
        image_path
            Path to the preprocessed image.

        plotting_area
            Dictionary containing:
            x
            y
            width
            height

        Returns
        -------
        dict
            Structured candlestick candidates.
        """

        image = self.image_service.load_image(image_path)

        x = plotting_area["x"]
        y = plotting_area["y"]
        w = plotting_area["width"]
        h = plotting_area["height"]

        roi = image[y:y + h, x:x + w]

        gray = cv2.cvtColor(
            roi,
            cv2.COLOR_BGR2GRAY,
        )

        _, binary = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        contours, _ = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        candidates = []

        index = 1

        for contour in contours:

            bx, by, bw, bh = cv2.boundingRect(contour)

            if bw < 2:
                continue

            if bh < 4:
                continue

            roi_colour = roi[
                by:by + bh,
                bx:bx + bw,
            ]

            mean_bgr = roi_colour.mean(axis=(0, 1))

            bullish = bool(
                mean_bgr[1] >= mean_bgr[2]
            )

            candidates.append(
                {
                    "id": index,
                    "position": {
                        "x": int(x + bx),
                        "y": int(y + by),
                    },
                    "width": int(bw),
                    "height": int(bh),
                    "colour": (
                        "bullish"
                        if bullish
                        else "bearish"
                    ),
                }
            )

            index += 1

        candidates.sort(
            key=lambda candle: candle["position"]["x"]
        )

        return {
            "status": "success",
            "candidate_count": len(candidates),
            "plotting_area": plotting_area,
            "candlesticks": candidates,
        }
