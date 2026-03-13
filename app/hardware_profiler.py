import psutil
import cpuinfo
import onnxruntime as ort
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HardwareProfiler")

class HardwareProfiler:
    def __init__(self):
        self.tier = 3
        self.config = {
            "inference_resolution": (160, 160),
            "skip_frames": 3,
            "blur_type": "pixelate",
            "execution_provider": "CPUExecutionProvider",
            "performance_tier": 3
        }

    def probe_system(self):
        """
        Probes the system hardware (CPU, GPU, RAM) and ONNX providers
        to determine the Performance Tier.
        """
        logger.info("Probing system hardware...")
        
        # 1. Check ONNX Providers (GPU detection)
        available_providers = ort.get_available_providers()
        logger.info(f"Available ONNX Providers: {available_providers}")
        
        has_cuda = 'CUDAExecutionProvider' in available_providers
        has_coreml = 'CoreMLExecutionProvider' in available_providers
        has_openvino = 'OpenVINOExecutionProvider' in available_providers
        has_directml = 'DmlExecutionProvider' in available_providers
        
        # 2. Check CPU capabilities
        cpu_info = cpuinfo.get_cpu_info()
        cpu_brand = cpu_info.get('brand_raw', 'Unknown CPU')
        logger.info(f"CPU: {cpu_brand}")
        
        # 3. Check RAM
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        logger.info(f"RAM: {ram_gb:.2f} GB")

        # 4. Core count
        physical_cores = psutil.cpu_count(logical=False)
        logical_cores = psutil.cpu_count(logical=True)
        logger.info(f"Cores: {physical_cores} physical, {logical_cores} logical")

        # Determine Tier
        if has_cuda or has_coreml:
            self._set_tier_1(available_providers)
        elif has_openvino or has_directml:
            self._set_tier_2(available_providers)
        elif physical_cores >= 8 or ram_gb >= 16:
            # Strong CPU can handle Tier 2 settings even on CPUExecutionProvider
            logger.info("Strong CPU detected, assigning Tier 2 (CPU-based)")
            self._set_tier_2(available_providers)
        else:
            self._set_tier_3()

        logger.info(f"System assigned to Performance Tier: {self.tier}")
        return self.config

    def _set_tier_1(self, providers):
        """High-End (Dedicated GPU / CUDA / Metal)"""
        self.tier = 1
        if 'CUDAExecutionProvider' in providers:
            provider = 'CUDAExecutionProvider'
        elif 'CoreMLExecutionProvider' in providers:
            provider = 'CoreMLExecutionProvider'
        else:
            provider = 'CPUExecutionProvider'
        
        self.config = {
            "inference_resolution": (640, 640), # High resolution
            "skip_frames": 0,                   # Run every frame
            "blur_type": "gaussian",            # High quality blur
            "execution_provider": provider,
            "performance_tier": 1
        }

    def _set_tier_2(self, providers):
        """Medium (Modern iGPU / Strong CPU)"""
        self.tier = 2
        if 'OpenVINOExecutionProvider' in providers:
            provider = 'OpenVINOExecutionProvider'
        elif 'DmlExecutionProvider' in providers:
            provider = 'DmlExecutionProvider'
        else:
            provider = 'CPUExecutionProvider'

        self.config = {
            "inference_resolution": (320, 320), # Medium resolution
            "skip_frames": 1,                   # Run every 2nd frame
            "blur_type": "gaussian",            # Still use Gaussian if possible
            "execution_provider": provider,
            "performance_tier": 2
        }

    def _set_tier_3(self, providers=None):
        """Low-End (CPU Only / Legacy)"""
        self.tier = 3
        self.config = {
            "inference_resolution": (160, 160), # Low resolution
            "skip_frames": 3,                   # Run every 4th frame
            "blur_type": "pixelate",            # Cheap pixelation
            "execution_provider": "CPUExecutionProvider",
            "performance_tier": 3
        }

if __name__ == "__main__":
    profiler = HardwareProfiler()
    config = profiler.probe_system()
    print("Final Config:", config)
