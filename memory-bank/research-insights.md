# Research Insights on Canon EDSDK Live View Implementation

## Critical Observation on EDSDK Sample Code (May 21, 2025)

Upon closer analysis of the EDSDK sample code (Page 191 - startLiveview function), we discovered a significant discrepancy between our implementation and the official sample:

```c
// Get the output device for the live view image
EdsUInt32 device;
err = EdsGetPropertyData(camera, kEdsPropID_Evf_OutputDevice, 0 , sizeof(device), &device );

// PC live view starts by setting the PC as the output device for the live view image.
if(err == EDS_ERR_OK)
{
    device |= kEdsEvfOutputDevice_PC;
    err = EdsSetPropertyData(camera, kEdsPropID_Evf_OutputDevice, 0 , sizeof(device), &device);
}

// A property change event notification is issued from the camera if property settings are made successfully.
// Start downloading of the live view image once the property change notification arrives.
// (SAMPLE10 then proceeds to EdsCreateMemoryStream, EdsCreateEvfImageRef, then EdsDownloadEvfImage inside a loop
// that implies events are being handled elsewhere or that the main thread is processing them)
```

### Key Insight

**The sample code does not explicitly set `kEdsPropID_Evf_Mode`.**

Our implementation has been explicitly setting `kEdsPropID_Evf_Mode` to `kEdsEvfMode_Enable` (value 1) after setting `kEdsPropID_Evf_OutputDevice`. However, the sample code suggests that this step might be unnecessary or even problematic.

### Hypothesis

By setting `kEdsPropID_Evf_OutputDevice` to include PC (value 3), the camera might automatically:
1. Enable the necessary internal live view mode, or
2. Prepare to do so upon the first attempt to download an EVF image

Explicitly trying to set `kEdsPropID_Evf_Mode` after `Evf_OutputDevice` is already set to include PC might be:
- Redundant
- Considered an invalid sequence by the camera (leading to Error 129)

### Progression of Issues

1. Initial attempts: Set `kEdsPropID_Evf_OutputDevice` directly to PC (value 2)
   - Validation logic incorrectly expected exactly value 2, but got 3
   - When proceeding despite this "error", `kEdsPropID_Evf_Mode` could be set successfully
   - Later failed with Error 97 (`EDS_ERR_OBJECT_NOTREADY`) during download

2. After fixing validation logic: 
   - Correctly confirmed PC bit is set in value 3
   - But now consistently failing with Error 129 (`EDS_ERR_INVALID_FN_CALL`) when setting `kEdsPropID_Evf_Mode`

3. After removing explicit `Evf_Mode` set:
   - No more Error 129 when setting `kEdsPropID_Evf_Mode` (since we're not setting it)
   - But still encountering Error 97 (`EDS_ERR_OBJECT_NOTREADY`) during download

## Critical Insight on EDSDK Event Handling (May 21, 2025)

The EDSDK documentation specifically states:

> "A property change event notification is issued from the camera if property settings are made successfully. Start downloading of the live view image once the property change notification arrives."

This suggests that after setting `kEdsPropID_Evf_OutputDevice`, we should:

1. Wait for a property change event notification for `kEdsPropID_Evf_OutputDevice`
2. Only then proceed to download the EVF image

Our initial approach of sleeping for a fixed time or processing a fixed number of events doesn't guarantee that we've received this specific notification before attempting the download.

### Implementation Approach

We've enhanced the event handling system to specifically track property change events for `kEdsPropID_Evf_OutputDevice`:

1. Added a property event handler that detects when the `kEdsPropID_Evf_OutputDevice` property changes
2. Implemented a `threading.Event` mechanism to signal when this specific event is detected
3. Added a wait loop that specifically waits for this event with a timeout
4. Only proceed to download the EVF image after this event is received or the timeout occurs

This targeted approach more closely follows the EDSDK's documentation and should increase the reliability of our live view implementation.

## SOLUTION CONFIRMED (November 12, 2025)

Based on Canon's official SAMPLE10 implementation, the correct approach is:
1. **DO NOT set kEdsPropID_Evf_Mode explicitly** - This causes Error 129 (Device Busy)
2. **Only set kEdsPropID_Evf_OutputDevice with PC bit** - This is sufficient to enable live view
3. **Process events after setting output device** - Allow camera time to apply changes

The key insight: Setting EVF output device to PC automatically enables the necessary live view mode internally. Explicitly setting Evf_Mode is redundant and causes conflicts.

## Previous Investigation (May 21, 2025)

The implementation now:
1. Correctly sets `kEdsPropID_Evf_OutputDevice` with a bitwise OR operation
2. Waits specifically for the property change notification
3. Does not explicitly set `kEdsPropID_Evf_Mode`
4. Includes robust retry logic for the download step

We're waiting to see if these changes resolve the persistent Error 97 during download.
