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
                    main.load_config(), ('poe', 'poe', 43, 41, 1, 3, 50, True, 0)
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
                ('waveshare-1.3', 'none', 43.0, 41.0, 1.0, 3.0, 50, True, 0.0)
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
        # Test 128x64 with fan disabled
        poe_nofan = util.PoeHatB(fan_type="none")
        poe_nofan.render_page_3_64(draw, 45.0, 43.0, 41.0)
        poe_nofan.render_page_3(draw, 45.0, 43.0, 41.0)

    def test_sh1106_driver(self):
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
             patch.object(self.poe, 'update_fan'):
            self.poe.poe_hat_display(43, 41, page_interval=3.0)
            self.assertEqual(self.poe.page_index, 0)

        with patch.object(util.time, 'monotonic', return_value=103.5), \
             patch.object(self.poe, 'update_fan'):
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

        poe.fan_mode = 1
        with patch.object(util.time, 'monotonic', return_value=21), \
             patch.object(poe, 'update_fan', return_value=35):
            poe.poe_hat_display(43, 41)
        display.wake.assert_called_once()
        display.ShowImage.assert_called_once()
        self.assertTrue(poe.screen_on)

    def test_manual_wake_expires(self):
        poe = util.PoeHatB(screen_timeout=10)
        with patch.object(util.time, 'monotonic', return_value=100):
            poe.request_wake(60)
        self.assertEqual(poe.manual_wake_until, 160)

    def test_pixel_shift_advances_on_page_rotation(self):
        self.poe.page_index = 0
        self.poe.last_page_switch = 100
        self.poe.shift_index = 4
        display = Mock(width=128, height=32)
        display.getbuffer.return_value = [0] * 512
        self.poe.show = display
        with patch.object(util.time, 'monotonic', return_value=103.5), \
             patch.object(self.poe, 'update_fan'), \
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


if __name__ == '__main__':
    unittest.main()
