# Canon Camera Connection Cleanup Protocol

## Current System Status Detection

1. Check USB Connection:
```bash
system_profiler SPUSBDataType | grep -A 10 -B 10 Canon
```
This shows if the camera is physically detected and provides:
- Product ID: 0x32da (13018)
- Vendor ID: 0x04a9 (1193)
- Connection speed and power requirements

2. Check Detailed USB Device Info:
```bash
ioreg -p IOUSB -l -w 0 | grep -A 20 -B 20 Canon
```
This provides detailed USB device information including:
- Device capabilities
- Power states
- USB configurations
- Serial number
- Location ID

3. Check Running Canon Processes:
```bash
ps aux | grep -i canon
```
Known processes that might interfere:
- Canon EOS Webcam Utility (`com.canon.cusa.eoswebcam.cameraExtension`)
- Other Canon software daemons

## Connection Cleanup Steps

Before initializing EDSDK connection:

1. Stop Canon EOS Webcam Utility:
```bash
sudo pkill -f "com.canon.cusa.eoswebcam"
```

2. Reset USB Device (if needed):
```bash
# Command to be determined - needs testing
```

3. Clear any existing camera locks:
```bash
# Command to be determined - needs testing
```

## Integration Notes

- These cleanup steps should be integrated into the camera initialization process
- Consider adding a pre-connection check routine
- May need to implement graceful fallbacks if cleanup commands fail
- Should add logging for connection/cleanup attempts

## TODO

- [ ] Test USB reset commands
- [ ] Determine if additional Canon processes need to be stopped
- [ ] Create a Python wrapper for these cleanup steps
- [ ] Add error handling for each step
- [ ] Test on different macOS versions
