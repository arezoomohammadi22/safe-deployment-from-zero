"""Run from 04-monitoring-rollback: python3 -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/'scripts'))
sys.path.insert(0, str(HERE.parent/'demo-app'))
from traffic_control import current_profile, set_profile
from rollback_controller import evaluate, query_scalar, ERRORS, TOTAL
from app.metrics import Registry

class TestMetrics(unittest.TestCase):
    def test_increment_and_cumulative_histogram(self):
        metrics=Registry()
        metrics.observe('POST','/api/checkout',503,'v2',0.020)
        out=metrics.render('v2',True).decode()
        self.assertIn('shop_http_requests_total{method="POST",route="/api/checkout",status="503",app_version="v2"} 1',out)
        self.assertIn('le="0.01"} 0',out)
        self.assertIn('le="0.025"} 1',out)
        self.assertIn('shop_fault_injection_enabled{app_version="v2"} 1',out)

    def test_zero_error_series_is_present(self):
        out=Registry().render('v1',False).decode()
        self.assertIn('status="503",app_version="v1"} 0',out)

class TestTrafficControl(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'nginx').mkdir()
        for name in ('95-5','80-20','100-0','0-100'):
            (self.root/'nginx'/f'{name}.conf').write_text(name)
        (self.root/'nginx/active.conf').write_text('95-5')

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_dry_run_does_not_modify(self):
        self.assertFalse(set_profile('100-0',root=self.root))
        self.assertEqual(current_profile(self.root),'95-5')

    @patch('traffic_control.subprocess.run')
    def test_execute_reloads_validated_nginx(self,mock_run):
        self.assertTrue(set_profile('100-0',root=self.root,execute=True))
        self.assertEqual(current_profile(self.root),'100-0')
        self.assertEqual(mock_run.call_count,2)

    @patch('traffic_control.subprocess.run')
    def test_nginx_validation_failure_restores_previous(self,mock_run):
        import subprocess
        mock_run.side_effect=[subprocess.CalledProcessError(1,'nginx -t'), None, None]
        with self.assertRaises(RuntimeError):
            set_profile('100-0',root=self.root,execute=True)
        self.assertEqual(current_profile(self.root),'95-5')

class TestPrometheusController(unittest.TestCase):
    @patch('rollback_controller.urlopen')
    def test_query_scalar_parsing(self,urlopen):
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=json.dumps({'status':'success','data':{'resultType':'vector','result':[{'value':[1,'7.5']}]}}).encode()
        response.__iter__.return_value=iter([])
        # json.load calls .read(), which is mocked
        urlopen.return_value=response
        self.assertEqual(query_scalar('http://localhost:19090',ERRORS),7.5)

    @patch('rollback_controller.set_profile')
    @patch('rollback_controller.current_profile',return_value='95-5')
    @patch('rollback_controller.query_scalar',side_effect=[4.0,12.0])
    def test_detects_failure_and_requests_rollback(self,query,profile,apply):
        apply.return_value=True
        self.assertTrue(evaluate('http://localhost',3,5,execute=True))
        apply.assert_called_once_with('100-0',execute=True)

    @patch('rollback_controller.set_profile')
    @patch('rollback_controller.query_scalar',side_effect=[1.0,12.0])
    def test_below_threshold_no_rollback(self,query,apply):
        self.assertFalse(evaluate('http://localhost',3,5,execute=True))
        apply.assert_not_called()

if __name__ == '__main__':
    unittest.main()
