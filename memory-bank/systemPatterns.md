# System Architecture and Patterns for Canon Camera Connection

## Overall Architecture

The system uses a worker thread model to interact with the Canon EDSDK:

```
Main Application Thread <---> Command/Data Queues <---> EDSDK Worker Thread <---> Canon Camera
```

## Live View Initialization Sequence

According to the EDSDK documentation, the proper sequence for starting live view is:

1. Read current EVF output device value
2. Set EVF output device with PC bit via bitwise OR: `device |= kEdsEvfOutputDevice_PC`
3. Wait for property change event
4. Enable EVF mode by setting `kEdsPropID_Evf_Mode` to 1
5. Wait for property change event
6. Download EVF image data

## Error Handling Pattern

The code implements a pattern of:
1. Attempt operation
2. Check for specific error codes
3. Revert settings on failure
4. Log detailed information about the failure

## Thread Safety

All EDSDK calls are protected with a lock (`self._event_lock`) to ensure thread safety when interacting with the SDK.
