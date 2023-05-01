
For installation you must run the following commands.

#### Enable I2C Interface

1. Run this command:
   ```sh
   sudo raspi-config
   ```
2. Select Interfacing Options > I2C.
3. Select Yes when prompted to enable the I2C interface.
4. Select Yes when prompted to automatically load the I2C kernel module.
5. Select Finish.
6. Select Yes when prompted to reboot.

#### Installation

<!--sec data-title="List files and directories: OS X and Linux" data-id="OSX_Linux_ls" data-collapse=true ces-->
    wget https://github.com/gokhancakal/poe_hat_b/archive/refs/heads/master.zip \
    && unzip -o  master.zip -d . \
    && cd poe_hat_b-master \
    && chmod +x install.sh \
    && ./install.sh
<!--endsec-->

#### Resources

1.  [waveshare PoE HAT (B)](https://www.waveshare.com/wiki/PoE_HAT_(B))