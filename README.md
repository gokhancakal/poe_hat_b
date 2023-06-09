
This installation is designed for **Power Over Ethernet HAT (Type B)** OLED and FAN control for Ubuntu OS.

For installation you must run the following commands.

#### Enable I2C Interface

1. Run this command:
   ```sh
   sudo apt-get install raspi-config
   sudo raspi-config
   ```
2. Select Interfacing Options > I2C.
3. Select Yes when prompted to enable the I2C interface.
4. Select Yes when prompted to automatically load the I2C kernel module.
5. Select Finish.
6. Select Yes when prompted to reboot.

#### Installation

<!--sec data-title="List files and directories: OS X and Linux" data-id="OSX_Linux_ls" data-collapse=true ces-->
    sudo apt install wget unzip -y \
    && sudo wget https://github.com/gokhancakal/poe_hat_b/archive/refs/heads/master.zip \
    && sudo unzip -o  master.zip -d . \
    && cd poe_hat_b-master \
    && sudo chmod +x install.sh \
    && sudo ./install.sh
<!--endsec-->

#### Resources

1.  [waveshare PoE HAT (B)](https://www.waveshare.com/wiki/PoE_HAT_(B))