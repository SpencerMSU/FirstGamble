# Update Instructions

To update the system and fix the "missing library" (httpx) error, follow these steps:

1.  Open a terminal on the server.
2.  Navigate to the project directory:
    ```bash
    cd /root/First/FirstGamble
    ```
3.  Run the update script:
    ```bash
    ./update.sh
    ```

This script will automatically:
1.  Pull the latest code from Git.
2.  Install any missing Python libraries (including `httpx`) defined in `requirements.txt`.
3.  Restart the `firstgamble-api` service.

If you encounter any permission errors, try running with `sudo`:
```bash
sudo ./update.sh
```
