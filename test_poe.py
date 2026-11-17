import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
# No real I2C or SPI device is touched by these tests.
sys.modules['smbus'] = types.SimpleNamespace(SMBus=Mock())
sys.modules['spidev'] = types.SimpleNamespace(SpiDev=Mock())
try:
    import psutil
except ModuleNotFoundError:
    import time
    psutil_mock = types.SimpleNamespace(
        cpu_percent=Mock(return_value=15.0),
        virtual_memory=Mock(return_value=types.SimpleNamespace(percent=45.0)),
        boot_time=Mock(return_value=time.time() - 3600),
        Error=Exception,
    )
    sys.modules['psutil'] = psutil_mock
import util
import main
from drivers import SSD1306, SH1106
from PIL import Image, ImageFont


class PoeTests(unittest.TestCase):
    def setUp(self):
        self.bus = Mock()
        self.bus.read_byte.return_value = 255
        self.bus_patch = patch.object(util.smbus, 'SMBus', return_value=self.bus)
        self.bus_patch.start()
        self.addCleanup(self.bus_patch.stop)
        self.poe = util.PoeHatB()

    def test_thresholds_and_no_duplicate_writes(self):
        for temp, expected in [(42, 1), (41, 1), (40.9, 0),
                               (42, 0), (43, 1), (44, 1)]:
            with patch.object(self.poe, 'get_temp', return_value=temp):
                self.poe.update_fan(43, 41)
            self.assertEqual(self.poe.fan_mode, expected)
        self.assertEqual(self.bus.write_byte.call_count, 3)

    def test_temperature_failure_requests_on(self):
        self.poe.fan_off()
        with patch.object(self.poe, 'get_temp', side_effect=OSError('sensor')):
            self.assertIsNone(self.poe.update_fan(43, 41))
        self.assertEqual(self.poe.fan_mode, 1)

    def test_failed_fan_write_is_unknown_and_retried(self):
        self.poe.fan_off()
        self.bus.write_byte.side_effect = OSError('bus')
        with patch.object(self.poe, 'get_temp', return_value=60):
            self.poe.update_fan(43, 41)
        self.assertIsNone(self.poe.fan_mode)
        self.bus.write_byte.side_effect = None
        with patch.object(self.poe, 'get_temp', return_value=42):
            self.poe.update_fan(43, 41)
        self.assertEqual(self.poe.fan_mode, 1)

    def test_offline_and_oled_failure_do_not_stop_fan(self):
        self.poe.fan_off()
        with patch.object(self.poe, 'get_temp', return_value=60), \
             patch.object(self.poe, 'get_ip', side_effect=OSError('no route')), \
             patch.object(util.drivers, 'SSD1306', side_effect=OSError('OLED')):
            self.poe.poe_hat_display(43, 41)
            self.assertEqual(self.poe.fan_mode, 1)
        with patch.object(self.poe, 'get_temp', return_value=35):
            self.poe.poe_hat_display(43, 41)
        self.assertEqual(self.poe.fan_mode, 0)

    def test_display_retry_recovers(self):
        self.poe.display_retry_at = 30
        with patch.object(util.time, 'monotonic', return_value=31), \
             patch.object(self.poe, 'get_temp', return_value=42), \
             patch.object(self.poe, 'get_ip', return_value='192.168.100.100'), \
             patch.object(util.drivers, 'SSD1306') as display:
            display.return_value.width = 128
            display.return_value.height = 32
            self.poe.poe_hat_display(43, 41)
            display.return_value.Init.assert_called_once_with(50)
            display.return_value.ShowImage.assert_called_once()

    def test_close_requests_on_and_closes_buses(self):
        self.poe.fan_off()
        display = self.poe.show = Mock()
        self.poe.close()
        self.assertEqual(self.poe.fan_mode, 1)
        display.Closebus.assert_called_once()
        self.bus.close.assert_called_once()

    def test_cpu_first_sample_unavailable(self):
        with patch.object(util.psutil, 'cpu_percent', return_value=25) as cpu:
            self.assertIsNone(self.poe.get_cpu())
            self.assertEqual(self.poe.get_cpu(), 25)
            cpu.assert_called_with(None)

    def test_display_buffer_bytes_and_rotation(self):
        driver = SSD1306()
        image = Image.new('1', (128, 32), 'WHITE')
        self.assertEqual(driver.getbuffer(image), [0] * 512)
        image.putpixel((0, 31), 0)
        self.assertEqual(driver.getbuffer(image)[384], 128)
        rotated = Image.new('1', (32, 128), 'WHITE')
        rotated.putpixel((0, 0), 0)
        self.assertEqual(driver.getbuffer(rotated), driver.getbuffer(image))

    def test_text_fits_fixed_columns(self):
        font = getattr(ImageFont, 'load_default_imagefont', ImageFont.load_default)()
        for text, width in [('IP:255.255.255.255', 128), ('CPU:100%', 70),
                            ('RAM:100%', 58), ('FAN OFF', 58)]:
            self.assertLessEqual(font.getbbox(text)[2], width)

    def test_invalid_config_falls_back(self):
        from io import StringIO
        for config in ['[poe]\nfan_on_temp=nan\nfan_off_temp=41\ninterval=1',
                       '[poe]\nfan_on_temp=40\nfan_off_temp=41\ninterval=1',
                       '[poe]\nfan_on_temp=43\nfan_off_temp=41\ninterval=0',
                       '[poe]\nfan_on_temp=43\nfan_off_temp=41\ninterval=1\npage_interval=0',
                       '[poe]\ncontrast=256',
                       '[poe]\nscreen_timeout=-1',
                       '[poe]\npixel_shift=maybe']:
            with patch.object(main.Path, 'open', return_value=StringIO(config)):
                self.assertEqual(
                    main.load_config(), ('poe', 'poe', 43, 41, 1, 5, 50, True, 0)
                )

    def test_valid_config(self):
        from io import StringIO
        with patch.object(main.Path, 'open', return_value=StringIO(
                '[poe]\ndisplay=waveshare-1.3\nfan=none\nfan_on_temp=50\nfan_off_temp=45\ninterval=2\npage_interval=5\ncontrast=128\npixel_shift=false\nscreen_timeout=300')):
            self.assertEqual(
                main.load_config(),
                ('waveshare-1.3', 'none', 50, 45, 2, 5, 128, False, 300)
            )

    def test_partial_config_defaults(self):
        from io import StringIO
        with patch.object(main.Path, 'open', return_value=StringIO(
                '[poe]\ndisplay=waveshare-1.3\nfan=none')):
            self.assertEqual(
                main.load_config(),
                ('waveshare-1.3', 'none', 43.0, 41.0, 1.0, 5.0, 50, True, 60.0)
            )

    def test_fan_none_profile(self):
        poe_nofan = util.PoeHatB(fan_type="none")
        self.assertFalse(poe_nofan.fan_enabled)
        self.assertIsNone(poe_nofan.i2c)
        self.assertIsNone(poe_nofan.fan_mode)
        # update_fan should not touch i2c or fail
        with patch.object(poe_nofan, 'get_temp', return_value=60):
            temp = poe_nofan.update_fan(43, 41)
            self.assertEqual(temp, 60)
            self.assertIsNone(poe_nofan.fan_mode)
        # close should not write to i2c
        poe_nofan.close()

    def test_render_all_pages_64(self):
        from PIL import Image, ImageDraw
        img = Image.new('1', (128, 64), 'WHITE')
        draw = ImageDraw.Draw(img)
        self.poe.render_page_1_64(draw)
        self.poe.render_page_2_64(draw)
        self.poe.render_page_3_64(draw, 45.0, 43.0, 41.0)
        self.assertLessEqual(self.poe._get_text_width("FAN: ACTIVE"), 105)
        # Test 128x64 with fan disabled
        poe_nofan = util.PoeHatB(fan_type="none")
        poe_nofan.render_page_3_64(draw, 45.0, 43.0, 41.0)
        poe_nofan.render_page_3(draw, 45.0, 43.0, 41.0)

    def test_sh1106_driver(self):
        import drivers.sh1106 as sh1106
        gpio = Mock()
        gpio.BCM = 1
        gpio.OUT = 1
        with patch.object(sh1106, '_GPIO_LIB', 'RPi.GPIO'), \
             patch.object(sh1106, 'GPIO', gpio, create=True):
            driver = SH1106()
            img = Image.new('1', (128, 64), 'WHITE')
            buf = driver.getbuffer(img)
            self.assertEqual(len(buf), 1024)
            self.assertEqual(buf, [0] * 1024)
            driver.Init()
            driver.ClearBlack()
            driver.ClearWhite()
            driver.ShowImage(buf)
            driver.Closebus()

    def test_page_rotation(self):
        self.poe.page_index = 0
        self.poe.last_page_switch = 100.0
        mock_show = Mock(width=128, height=32)
        mock_show.getbuffer.return_value = [0] * 512
        self.poe.show = mock_show
        with patch.object(util.time, 'monotonic', return_value=101.0), \
             patch.object(self.poe, 'update_fan', return_value=35):
            self.poe.poe_hat_display(43, 41, page_interval=3.0)
            self.assertEqual(self.poe.page_index, 0)

        with patch.object(util.time, 'monotonic', return_value=103.5), \
             patch.object(self.poe, 'update_fan', return_value=35):
            self.poe.poe_hat_display(43, 41, page_interval=3.0)
            self.assertEqual(self.poe.page_index, 1)

    def test_screen_timeout_and_fan_wake(self):
        poe = util.PoeHatB(screen_timeout=10)
        poe.fan_mode = 0
        display = Mock(width=128, height=32)
        display.getbuffer.return_value = [0] * 512
        poe.show = display
        poe.last_active_time = 0

        with patch.object(util.time, 'monotonic', return_value=20), \
             patch.object(poe, 'update_fan', return_value=35):
            poe.poe_hat_display(43, 41)
        display.sleep.assert_called_once()
        display.ShowImage.assert_not_called()
        self.assertFalse(poe.screen_on)

        def turn_fan_on(*args):
            poe.fan_mode = 1
            return 35

        with patch.object(util.time, 'monotonic', return_value=21), \
             patch.object(poe, 'update_fan', side_effect=turn_fan_on):
            poe.poe_hat_display(43, 41)
        display.wake.assert_called_once()
        display.ShowImage.assert_called_once()
        self.assertTrue(poe.screen_on)

    def test_fan_does_not_prevent_display_timeout(self):
        poe = util.PoeHatB(screen_timeout=10)
        poe.fan_mode = 1
        poe.last_temp = 50
        display = Mock(width=128, height=32)
        poe.show = display
        poe.last_active_time = 0

        with patch.object(util.time, 'monotonic', return_value=10), \
             patch.object(poe, 'update_fan', return_value=50):
            poe.poe_hat_display(43, 41)
        display.sleep.assert_called_once()
        self.assertFalse(poe.screen_on)

        with patch.object(util.time, 'monotonic', return_value=11), \
             patch.object(poe, 'update_fan', return_value=50):
            poe.poe_hat_display(43, 41)
        display.wake.assert_not_called()
        self.assertFalse(poe.screen_on)

    def test_manual_wake_expires_at_60_seconds(self):
        poe = util.PoeHatB(screen_timeout=300)
        poe.fan_mode = 0
        display = Mock(width=128, height=32)
        poe.show = display
        poe.screen_on = False
        poe.last_active_time = 0
        with patch.object(util.time, 'monotonic', return_value=100):
            poe.request_wake(60)
        self.assertEqual(poe.manual_wake_until, 160)

        with patch.object(util.time, 'monotonic', return_value=159), \
             patch.object(poe, 'update_fan', return_value=35):
            poe.poe_hat_display(43, 41)
        self.assertTrue(poe.screen_on)
        display.sleep.assert_not_called()

        with patch.object(util.time, 'monotonic', return_value=160), \
             patch.object(poe, 'update_fan', return_value=35):
            poe.poe_hat_display(43, 41)
        display.sleep.assert_called_once()
        self.assertFalse(poe.screen_on)
        self.assertEqual(poe.manual_wake_until, 0)

    def test_sh1106_requires_gpio_and_spi(self):
        from unittest.mock import Mock
        import drivers.sh1106 as sh1106

        with patch.object(sh1106, '_GPIO_LIB', 'mock'), \
             self.assertRaisesRegex(RuntimeError, 'GPIO support'):
            SH1106()

        gpio = Mock()
        gpio.BCM = 1
        gpio.OUT = 1
        with patch.object(sh1106, '_GPIO_LIB', 'RPi.GPIO'), \
             patch.object(sh1106, 'GPIO', gpio, create=True), \
             patch.object(sh1106, 'spidev', None), \
             self.assertRaisesRegex(RuntimeError, 'spidev'):
            SH1106()

    def test_pixel_shift_advances_on_page_rotation(self):
        self.poe.page_index = 0
        self.poe.last_page_switch = 100
        self.poe.shift_index = 4
        display = Mock(width=128, height=32)
        display.getbuffer.return_value = [0] * 512
        self.poe.show = display
        with patch.object(util.time, 'monotonic', return_value=103.5), \
             patch.object(self.poe, 'update_fan', return_value=35), \
             patch.object(util.ImageChops, 'offset', wraps=util.ImageChops.offset) as offset:
            self.poe.poe_hat_display(43, 41, page_interval=3)
        self.assertEqual(self.poe.shift_index, 5)
        self.assertEqual(offset.call_args.args[1:], (1, 0))

    def test_render_all_pages(self):
        from PIL import Image, ImageDraw
        img = Image.new('1', (128, 32), 'WHITE')
        draw = ImageDraw.Draw(img)
        self.poe.render_page_1(draw)
        self.poe.render_page_2(draw)
        self.poe.render_page_3(draw, 45.0, 43.0, 41.0)

    def test_context_manager(self):
        with patch.object(self.poe, 'close') as mock_close:
            with self.poe as p:
                self.assertIs(p, self.poe)
            mock_close.assert_called_once()

    def test_ip_caching_and_error_invalidation(self):
        self.poe._ip_cache = None
        self.poe._ip_cache_at = 0
        with patch('socket.socket') as mock_sock:
            sock_inst = mock_sock.return_value.__enter__.return_value
            sock_inst.getsockname.return_value = ['192.168.1.50']
            ip1 = self.poe.get_ip()
            self.assertEqual(ip1, '192.168.1.50')
            self.assertEqual(mock_sock.call_count, 1)

            ip2 = self.poe.get_ip()
            self.assertEqual(ip2, '192.168.1.50')
            self.assertEqual(mock_sock.call_count, 1)

        with patch.object(self.poe, 'get_ip', side_effect=OSError('network down')):
            self.poe.poe_hat_display(43, 41)
            self.assertIsNone(self.poe._ip_cache)

    def test_get_memory(self):
        mem_mock = Mock(percent=45.6)
        with patch.object(util.psutil, 'virtual_memory', return_value=mem_mock):
            self.assertEqual(self.poe.get_memory(), 45.6)

    def test_get_temp_parsing(self):
        from io import StringIO
        with patch('builtins.open', return_value=StringIO(' 48250 \n')):
            self.assertAlmostEqual(self.poe.get_temp(), 48.25)

    def test_show_image_block_write(self):
        driver = SSD1306()
        driver.bus = Mock()
        driver.bus.write_i2c_block_data = Mock()
        buf = [0x55] * 512
        driver.ShowImage(buf)
        self.assertEqual(driver.bus.write_i2c_block_data.call_count, 16)

    def test_show_image_fallback_to_byte_write(self):
        driver = SSD1306()
        driver.bus = Mock()
        driver.bus.write_i2c_block_data.side_effect = OSError('Not supported')
        buf = [0x55] * 512
        driver.ShowImage(buf)
        self.assertGreaterEqual(driver.bus.write_byte_data.call_count, 512)

    def test_modular_packages(self):
        import drivers
        import controllers
        import renderers

        # Drivers
        self.assertTrue(issubclass(drivers.SSD1306, object))
        self.assertTrue(issubclass(drivers.SH1106, object))

        # Controllers
        dummy = controllers.get_fan_controller("none")
        self.assertIsInstance(dummy, controllers.DummyFanController)
        self.assertFalse(dummy.enabled)

        poe_ctl = controllers.get_fan_controller("poe")
        self.assertIsInstance(poe_ctl, controllers.PoeFanController)
        self.assertTrue(poe_ctl.enabled)

        # Renderers
        font = getattr(ImageFont, 'load_default_imagefont', ImageFont.load_default)()
        v32 = renderers.View128x32(font)
        v64 = renderers.View128x64(font)
        self.assertIsNotNone(v32)
        self.assertIsNotNone(v64)

        img = Image.new('1', (128, 32), 'WHITE')
        draw = Image.new('1', (128, 32), 'WHITE').load()
        from PIL import ImageDraw
        draw_obj = ImageDraw.Draw(img)
        renderers.draw_progress_bar(draw_obj, 0, 0, 50, 10, 50)
        self.assertGreater(renderers.get_text_width(font, "TEST"), 0)


class WaveshareTests(unittest.TestCase):
    def setUp(self):
        bus = Mock()
        bus.read_byte.return_value = 255
        bus_patch = patch.object(util.smbus, 'SMBus', return_value=bus)
        bus_patch.start()
        self.addCleanup(bus_patch.stop)
        from queue import SimpleQueue
        self.inputs = Mock(events=SimpleQueue())
        with patch.object(util, 'OLEDButtons', return_value=self.inputs):
            self.poe = util.PoeHatB(display_type='waveshare-1.3')
        self.poe.show = Mock(width=128, height=64)
        self.poe.last_active_time = 0
        self.poe.last_page_switch = 0

    def tick(self, now, action=None, temp=50, sample=True):
        if action:
            self.inputs.events.put(action)
        with patch.object(util.time, 'monotonic', return_value=now), \
             patch.object(self.poe, 'get_temp', return_value=temp):
            self.poe.poe_hat_display(43, 41, page_interval=3, sample=sample)

    def test_contrast_overlay_expires_without_extra_measurement(self):
        self.poe.page_index = 2
        with patch.object(self.poe.renderer_64, 'render_contrast') as overlay, \
             patch.object(self.poe, 'render_page_3_64') as page, \
             patch.object(self.poe, 'update_fan') as fan:
            self.tick(1, 'up', sample=False)
            overlay.assert_called_once()
            self.assertEqual(overlay.call_args.args[1], 75)
            self.tick(3, sample=False)
            self.assertEqual(self.poe.page_index, 2)
            page.assert_not_called()
            self.tick(4, sample=False)
            page.assert_called_once()
            self.assertEqual(self.poe.page_index, 2)
            self.assertEqual(self.poe.last_active_time, 1)
        fan.assert_not_called()

    def test_contrast_overlay_extends_and_preserves_manual_page(self):
        self.tick(1, 'key2')
        self.tick(2, 'up')
        self.tick(4, 'down')
        self.assertEqual(self.poe.contrast_until, 7)
        self.tick(7, sample=False)
        self.assertEqual(self.poe.contrast_until, 0)
        self.assertTrue(self.poe.manual_page)
        self.assertEqual(self.poe.page_index, 1)
        self.tick(20)
        self.assertEqual(self.poe.page_index, 1)

    def test_contrast_overlay_dismiss_and_wake_consumption(self):
        self.tick(1, 'up')
        self.tick(2, 'key3')
        self.assertEqual(self.poe.contrast_until, 0)
        self.tick(3, 'down')
        self.tick(4, 'center')
        self.assertEqual(self.poe.contrast_until, 0)
        contrast = self.poe.contrast
        self.tick(5, 'up')
        self.assertEqual(self.poe.contrast_until, 0)
        self.assertEqual(self.poe.contrast, contrast)

    def test_waveshare_timeout_with_running_fan(self):
        self.tick(59)
        self.assertTrue(self.poe.screen_on)
        self.tick(60)
        self.assertFalse(self.poe.screen_on)
        self.assertEqual(self.poe.fan_mode, 1)
        self.tick(61, temp=35)
        self.assertEqual(self.poe.fan_mode, 0)
        self.tick(62, temp=70)
        self.assertEqual(self.poe.fan_mode, 1)
        self.assertFalse(self.poe.screen_on)
        self.assertEqual(self.poe.last_active_time, 0)

    def test_waveshare_first_press_consumed_and_timeout_reset(self):
        self.tick(60)
        old_page = self.poe.page_index
        self.tick(61, 'key3')
        self.assertTrue(self.poe.screen_on)
        self.assertEqual(self.poe.page_index, old_page)
        self.tick(62, 'key3')
        self.assertEqual(self.poe.page_index, 2)
        self.tick(121)
        self.assertTrue(self.poe.screen_on)
        self.tick(122)
        self.assertFalse(self.poe.screen_on)

    def test_waveshare_pages_rotation_and_pixel_shift(self):
        for action, expected in [('key1', 0), ('key2', 1), ('key3', 2),
                                 ('right', 0), ('left', 2)]:
            self.tick(1, action)
            self.assertEqual(self.poe.page_index, expected)
        shift = self.poe.shift_index
        self.tick(20)
        self.assertEqual(self.poe.page_index, 2)
        self.assertNotEqual(self.poe.shift_index, shift)
        self.tick(21, 'center')
        self.assertFalse(self.poe.screen_on)
        self.tick(22, 'left')
        self.assertFalse(self.poe.manual_page)
        self.assertEqual(self.poe.page_index, 2)
        self.tick(25)
        self.assertEqual(self.poe.page_index, 0)

    def test_waveshare_brightness_bounds_and_first_press(self):
        for _ in range(10):
            self.tick(1, 'up')
        self.assertEqual(self.poe.contrast, 255)
        for _ in range(10):
            self.tick(2, 'down')
        self.assertEqual(self.poe.contrast, 10)
        self.tick(3, 'center')
        self.tick(4, 'up')
        self.assertEqual(self.poe.contrast, 10)
        self.poe.show.set_contrast.assert_called_with(10)

    def test_waveshare_input_does_not_sample_temperature_or_cpu(self):
        with patch.object(self.poe, 'update_fan') as fan, \
             patch.object(util.psutil, 'cpu_percent') as cpu:
            self.tick(1, 'key2', sample=False)
        fan.assert_not_called()
        cpu.assert_not_called()
        self.assertEqual(self.poe.page_index, 1)

    def test_held_button_does_not_repeat_or_extend_timeout(self):
        # A held gpiozero Button delivers one when_pressed event; subsequent
        # service ticks must neither repeat it nor renew activity.
        self.tick(1, 'right')
        for now in (2, 10, 30, 60):
            self.tick(now)
            self.assertEqual(self.poe.page_index, 1)
            self.assertEqual(self.poe.last_active_time, 1)
        self.tick(61)
        self.assertFalse(self.poe.screen_on)

    def test_waveshare_gpio_failure_keeps_fan(self):
        with patch.object(util, 'OLEDButtons', side_effect=RuntimeError('GPIO busy')), \
             self.assertLogs(level='WARNING') as logs:
            poe = util.PoeHatB(display_type='waveshare-1.3')
        self.assertIn('GPIO busy', logs.output[0])
        self.assertIsNone(poe.buttons)
        poe.show = Mock(width=128, height=64)
        poe.last_active_time = 0
        with patch.object(util.time, 'monotonic', return_value=60), \
             patch.object(poe, 'get_temp', return_value=70):
            poe.poe_hat_display(43, 41)
        self.assertEqual(poe.fan_mode, 1)
        self.assertFalse(poe.screen_on)

    def test_sleep_failure_retries_without_stopping_fan(self):
        for action, start in [(None, 60), ('center', 1)]:
            with self.subTest(action=action):
                self.poe.screen_on = True
                self.poe.last_active_time = 0
                self.poe.display_retry_at = 0
                old = self.poe.show = Mock(width=128, height=64)
                old.sleep.side_effect = OSError('SPI sleep failed')
                self.tick(start, action)
                self.assertFalse(self.poe.screen_on)
                self.assertTrue(self.poe.sleep_pending)
                replacement = Mock(width=128, height=64)
                with patch.object(util.drivers, 'SH1106', return_value=replacement) as driver:
                    self.tick(start + 1, temp=35)
                    driver.assert_not_called()
                    self.assertEqual(self.poe.fan_mode, 0)
                    self.tick(start + 30, temp=70)
                replacement.Init.assert_called_once_with(50)
                replacement.sleep.assert_called_once()
                replacement.ShowImage.assert_not_called()
                self.assertFalse(self.poe.sleep_pending)
                self.assertEqual(self.poe.fan_mode, 1)

    def test_timers_run_between_samples_without_sampling(self):
        self.poe.last_shift = 0
        with patch.object(self.poe, 'update_fan') as fan, \
             patch.object(self.poe, 'update_metrics') as metrics:
            for now, page in [(3, 1), (6, 2), (9, 0)]:
                self.tick(now, sample=False)
                self.assertEqual(self.poe.page_index, page)
            self.tick(10, 'key2', sample=False)
            shift = self.poe.shift_index
            self.tick(12, sample=False)
            self.assertEqual(self.poe.page_index, 1)
            self.assertNotEqual(self.poe.shift_index, shift)
        fan.assert_not_called()
        metrics.assert_not_called()
        self.assertEqual(self.poe.last_active_time, 10)

    def test_failed_button_wake_recovers_without_another_press(self):
        self.poe.screen_on = False
        self.poe.show.wake.side_effect = OSError('wake failed')
        self.tick(100, 'key2')
        self.assertTrue(self.poe.screen_on)
        self.assertEqual(self.poe.page_index, 0)  # First press consumed.
        self.assertEqual(self.poe.last_active_time, 100)
        replacement = Mock(width=128, height=64)
        with patch.object(util.drivers, 'SH1106', return_value=replacement) as driver:
            self.tick(129, temp=35)
            driver.assert_not_called()
            self.assertEqual(self.poe.fan_mode, 0)
            self.tick(130, temp=70)
        replacement.Init.assert_called_once_with(50)
        replacement.ShowImage.assert_called_once()
        self.assertEqual(self.poe.fan_mode, 1)
        self.assertEqual(self.poe.last_active_time, 100)
        self.tick(160)
        replacement.sleep.assert_called_once()

    def test_signal_wake_redraws_between_samples(self):
        self.poe.screen_on = False
        with patch.object(util.time, 'monotonic', return_value=100):
            self.poe.request_wake()
        with patch.object(self.poe, 'update_fan') as fan:
            self.tick(100, sample=False)
        self.poe.show.wake.assert_called_once()
        self.poe.show.ShowImage.assert_called_once()
        fan.assert_not_called()
        self.tick(101, sample=False)
        self.poe.show.ShowImage.assert_called_once()

    def test_explicit_zero_preserved(self):
        from io import StringIO
        with patch.object(main.Path, 'open', return_value=StringIO(
                '[poe]\ndisplay=waveshare-1.3\nscreen_timeout=0')):
            self.assertEqual(main.load_config()[-1], 0)


class ButtonTests(unittest.TestCase):
    def test_real_gpiozero_press_hold_release(self):
        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            self.skipTest('Install gpiozero for virtual GPIO integration test')
        from buttons import OLEDButtons, PINS
        factory = MockFactory()
        backend = types.SimpleNamespace(LGPIOFactory=lambda: factory)
        with patch.dict(sys.modules, {'gpiozero.pins.lgpio': backend}):
            inputs = OLEDButtons()
        self.addCleanup(inputs.close)
        for action, pin_number in PINS.items():
            pin = factory.pin(pin_number)
            self.assertEqual(pin.bounce, 0.05)
            pin.drive_low()
            self.assertEqual(inputs.events.get_nowait(), action)
            for _ in range(10):
                pin.drive_low()
            self.assertTrue(inputs.events.empty())
            pin.drive_high()
            self.assertTrue(inputs.events.empty())
            pin.drive_low()
            self.assertEqual(inputs.events.get_nowait(), action)
            pin.drive_high()
        # MockPin does not implement electrical debounce; this verifies the
        # real Button callback/edge/hold behavior and configured bounce time.

    def test_callbacks_enqueue_and_cleanup_partial_initialization(self):
        import buttons
        devices = [Mock() for _ in buttons.PINS]
        constructor = Mock(side_effect=devices)
        factory = Mock()
        modules = {'gpiozero': types.SimpleNamespace(Button=constructor),
                   'gpiozero.pins': types.ModuleType('gpiozero.pins'),
                   'gpiozero.pins.lgpio': types.SimpleNamespace(LGPIOFactory=Mock(return_value=factory))}
        with patch.dict(sys.modules, modules):
            inputs = buttons.OLEDButtons()
        self.assertTrue(inputs.events.empty())
        for (action, pin), device, call in zip(buttons.PINS.items(), devices, constructor.call_args_list):
            self.assertEqual(call.args, (pin,))
            self.assertEqual(call.kwargs['bounce_time'], 0.05)
            self.assertTrue(call.kwargs['pull_up'])
            device.when_pressed()
            self.assertEqual(inputs.events.get_nowait(), action)
            # No hold callback: gpiozero only invokes when_pressed on an edge.
            self.assertNotIn('when_held', device.__dict__)
        inputs.close()
        for device in devices:
            device.close.assert_called_once()
        factory.close.assert_called_once()
        first = Mock()
        constructor.side_effect = [first, RuntimeError('pin busy')]
        with patch.dict(sys.modules, modules), self.assertRaisesRegex(RuntimeError, 'pin busy'):
            buttons.OLEDButtons()
        first.close.assert_called_once()


class RegressionTests(unittest.TestCase):
    def test_installer_profile_precedence(self):
        import os
        import shutil
        import subprocess
        import tempfile
        bash = ('C:/Program Files/Git/usr/bin/bash.exe' if os.name == 'nt'
                else shutil.which('bash'))
        if not bash or not Path(bash).exists():
            self.skipTest('Bash required')
        source = Path(__file__).with_name('install.sh').read_text()
        # Exercise only profile selection, never the privileged installer body.
        selection = source[source.index('# Select the same config'):source.index('echo "Installing')]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app, src = root / 'app', root / 'source'
            app.mkdir(); src.mkdir()
            (src / 'config.ini').write_text('[poe]\nDISPLAY=waveshare-1.3\nFAN=none\n')
            env = dict(os.environ, APP=app.as_posix(), SOURCE_DIR=src.as_posix(),
                       TEST_PYTHON=Path(sys.executable).as_posix())
            if os.name == 'nt':
                env['PATH'] = 'C:/Program Files/Git/usr/bin;C:/Program Files/Git/bin;' + env.get('PATH', '')
            for installed, explicit, expected in [(False, False, 'waveshare-1.3 none'),
                                                    (False, True, 'poe poe'),
                                                    (True, False, 'poe poe')]:
                if installed:
                    (app / 'config.ini').write_text('[poe]\ndisplay=poe\nfan=poe\n')
                script = ('python3() { "$TEST_PYTHON" "$@"; }\n'
                          'DISPLAY_TYPE=poe\nFAN_TYPE=poe\n'
                          f'EXPLICIT_DISPLAY={int(explicit)}\nEXPLICIT_FAN={int(explicit)}\n'
                          + selection + '\nprintf "%s %s" "$DISPLAY_TYPE" "$FAN_TYPE"')
                result = subprocess.run([bash, '-c', script], env=env,
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout, expected)

    def test_invalid_setting_preserves_other_values(self):
        from io import StringIO
        with patch.object(main.Path, 'open', return_value=StringIO(
                '[poe]\ndisplay=waveshare-1.3\nfan=none\ncontrast=bad\ninterval=2\nscreen_timeout=0')):
            cfg = main.load_config()
        self.assertEqual(cfg[:2], ('waveshare-1.3', 'none'))
        self.assertEqual((cfg[4], cfg[6], cfg[8]), (2, 50, 0))

    def test_partial_spi_and_gpio_initialization_closes_resources(self):
        import drivers.sh1106 as module
        rst, dc = Mock(), Mock()
        gpiozero = types.SimpleNamespace(OutputDevice=Mock(side_effect=[rst, dc]))
        with patch.dict(sys.modules, {'gpiozero': gpiozero}), \
             patch.object(module, '_GPIO_LIB', 'gpiozero'), \
             patch.object(module, 'spidev', None):
            with self.assertRaises(RuntimeError):
                SH1106()
        rst.close.assert_called_once()
        dc.close.assert_called_once()
        rst.reset_mock()
        gpiozero.OutputDevice.side_effect = [rst, OSError('DC busy')]
        with patch.dict(sys.modules, {'gpiozero': gpiozero}), \
             patch.object(module, '_GPIO_LIB', 'gpiozero'):
            with self.assertRaises(RuntimeError):
                SH1106()
        rst.close.assert_called_once()

    def test_ssd1306_partial_block_failure_restarts_page(self):
        driver = SSD1306()
        driver.bus = Mock()
        driver.bus.write_i2c_block_data.side_effect = [None, OSError('second block')]
        driver.ShowImage([0x55] * 512)
        calls = driver.bus.mock_calls
        from unittest.mock import call
        failure = calls.index(call.write_i2c_block_data(0x3c, 0x40, [0x55] * 32), 4)
        self.assertEqual(calls[failure + 1:failure + 5], [
            call.write_byte_data(0x3c, 0, 0xb0),
            call.write_byte_data(0x3c, 0, 0),
            call.write_byte_data(0x3c, 0, 0x10),
            call.write_byte_data(0x3c, 0x40, 0x55)])

    def test_metrics_sample_even_when_asleep(self):
        poe = util.PoeHatB(fan_type='none')
        poe.screen_on = False
        with patch.object(poe, 'get_temp', return_value=35), \
             patch.object(poe, 'get_cpu', return_value=55) as cpu, \
             patch.object(poe, 'get_memory', return_value=45) as memory:
            poe.poe_hat_display(43, 41)
            poe.poe_hat_display(43, 41, sample=False)
        cpu.assert_called_once()
        memory.assert_called_once()
        self.assertEqual((poe.cached_cpu, poe.cached_memory), (55, 45))

    def test_brightness_outside_steps_never_reverses_direction(self):
        from queue import SimpleQueue
        with patch.object(util, 'OLEDButtons', return_value=Mock(events=SimpleQueue())):
            poe = util.PoeHatB(display_type='waveshare-1.3', fan_type='none')
        for initial, action, expected in [(200, 'up', 255), (200, 'down', 150),
                                           (1, 'down', 1), (1, 'up', 10)]:
            poe.contrast = initial
            poe.buttons.events.put(action)
            poe.process_buttons(1)
            self.assertEqual(poe.contrast, expected)

    def test_render_text_bounds_and_unknown_status(self):
        from renderers import View128x32, View128x64
        font = getattr(ImageFont, 'load_default_imagefont', ImageFont.load_default)()
        for renderer, height in [(View128x32(font), 32), (View128x64(font), 64)]:
            for page in (1, 2, 3):
                draw = Mock()
                if page == 1:
                    renderer.render_page_1(draw, '255.255.255.255', 'hostname' * 10, '12345d 23h 59m')
                elif page == 2:
                    renderer.render_page_2(draw, None, None)
                    self.assertIn('LOAD UNKNOWN', [c.args[1] for c in draw.text.call_args_list])
                else:
                    renderer.render_page_3(draw, 100, 0, 85, 84)
                boxes = []
                for c in draw.text.call_args_list:
                    (x, y), text = c.args
                    from PIL import ImageDraw
                    ink = Image.new('1', (256, 32), 0)
                    ImageDraw.Draw(ink).text((0, 0), text, font=font, fill=1)
                    left, top, right, bottom = ink.getbbox()
                    box = (x+left, y+top, x+right, y+bottom)
                    self.assertGreaterEqual(box[0], 1)
                    self.assertLessEqual(box[2], 127)
                    self.assertLessEqual(box[3], height-1)
                    for other in boxes:
                        self.assertFalse(box[0] < other[2] and other[0] < box[2]
                                         and box[1] < other[3] and other[1] < box[3], (box, other))
                    boxes.append(box)
        draw = Mock()
        View128x64(font).render_page_1(draw, '--', 'pi', '1h')
        self.assertIn('IP UNKNOWN', [c.args[1] for c in draw.text.call_args_list])


if __name__ == '__main__':
    unittest.main()
