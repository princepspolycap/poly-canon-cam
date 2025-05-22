# Active Context for Canon Camera Live View Implementation

## Current Progress

1.  Successfully set `kEdsPropID_Evf_OutputDevice` using bitwise OR, and validated the PC bit correctly (value 3).
2.  **Removed the explicit call to `EdsSetPropertyData` for `kEdsPropID_Evf_Mode`**, aligning with EDSDK sample code. This resolved the immediate Error 129 that was occurring at that step.
3.  Implemented enhanced event processing loop (2 seconds) after setting `kEdsPropID_Evf_OutputDevice`.
4.  Maintained retry mechanism for `EDS_ERR_OBJECT_NOTREADY` during `EdsDownloadEvfImage`.

## Current Issues (Based on logs after removing explicit Evf_Mode set)

1.  **Primary Blocker**: `EdsDownloadEvfImage` consistently fails with Error 97 (`EDS_ERR_OBJECT_NOTREADY`) during the priming download attempt, even after the 2-second event processing loop. This occurs on the first attempt within the retry logic.
2.  **Secondary Issue (during revert)**: Attempting to disable `kEdsPropID_Evf_Mode` in `_revert_live_view_settings_on_failure` now results in Error 129. This is likely because `kEdsPropID_Evf_Mode` was not explicitly enabled by our code in this new flow.

## Next Steps (Based on User Analysis)

1.  **Focus on Event Processing for Readiness**: The immediate priority is to resolve Error 97. The camera is not ready for `EdsDownloadEvfImage` after `kEdsPropID_Evf_OutputDevice` is set and the current event processing.
    *   Investigate how to specifically detect the "property change notification" for `kEdsPropID_Evf_OutputDevice` as mentioned in the EDSDK documentation.
    *   The event processing loop after setting `Evf_OutputDevice` needs to be more targeted or potentially longer, or wait for a specific event type/property ID that signals readiness for download.
2.  **Refine Revert Logic**: Once live view start is successful, revisit `_revert_live_view_settings_on_failure` to correctly handle the state where `kEdsPropID_Evf_Mode` was not explicitly set by our application. For now, the focus is on successful startup.
3.  **Consider Camera State**: If Error 97 persists, we might need to query other camera properties after setting `Evf_OutputDevice` to understand its state better or see if `kEdsPropID_Evf_Mode` changes automatically.
