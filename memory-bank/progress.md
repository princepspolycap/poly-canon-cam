# Progress Log for Canon Camera Live View Implementation

## ✅ Completed

- Camera connection and session management.
- Basic camera properties retrieval.
- Initial implementation of live view initialization.
- **Corrected `kEdsPropID_Evf_OutputDevice` setting**: Now uses bitwise OR and validates the PC bit correctly (value 3 is accepted).
- **Aligned with EDSDK Sample for `kEdsPropID_Evf_Mode`**: Removed the explicit setting of `kEdsPropID_Evf_Mode`. This resolved an Error 129 that was occurring immediately after setting `Evf_OutputDevice`.
- Maintained retry mechanism for `EDS_ERR_OBJECT_NOTREADY` during `EdsDownloadEvfImage`.

## ⏳ In Progress

- **Resolving Error 97 (`EDS_ERR_OBJECT_NOTREADY`)**: This is now the primary blocker. It occurs during the priming `EdsDownloadEvfImage` call, even after a 2-second event processing loop following the `kEdsPropID_Evf_OutputDevice` set.
- **Refining Event Processing**: The key focus is to correctly wait for and detect the "property change notification" for `kEdsPropID_Evf_OutputDevice` before attempting to download the EVF image, as suggested by EDSDK documentation.

## 🐛 Known Issues

1.  **Critical**: `EdsDownloadEvfImage` consistently fails with Error 97 (`EDS_ERR_OBJECT_NOTREADY`) after setting `kEdsPropID_Evf_OutputDevice` and processing events for 2 seconds. The camera is not yet ready for image download.
2.  **Secondary (Revert Logic)**: Attempting to disable `kEdsPropID_Evf_Mode` in `_revert_live_view_settings_on_failure` now causes Error 129. This is because `Evf_Mode` was not explicitly enabled by our code in the current flow. (This is lower priority than successful startup).

## 📝 Evolution of Approach

Initial approach:
- Set `Evf_OutputDevice` directly to PC (value 2).
- Explicitly enable `Evf_Mode`.
- Attempt download. (Led to various errors, including misinterpretation of `Evf_OutputDevice` value 3).

Revised approach 1 (after fixing `Evf_OutputDevice` ORing and validation):
- Correctly set `Evf_OutputDevice` to 3 (TFT | PC).
- Explicitly enable `Evf_Mode`. (This step started failing with Error 129).
- Attempt download.

Revised approach 2 (current, aligning with EDSDK sample):
- Correctly set `Evf_OutputDevice` to 3.
- **Removed explicit `Evf_Mode` set.** (This resolved the Error 129 at that specific point).
- Process events for 2 seconds.
- Attempt download. (Now consistently fails with Error 97).

Next refinement:
- Implement a more targeted event processing mechanism after setting `Evf_OutputDevice` to specifically wait for the `kEdsPropertyEvent_PropertyChanged` notification for `kEdsPropID_Evf_OutputDevice` before attempting `EdsDownloadEvfImage`.
