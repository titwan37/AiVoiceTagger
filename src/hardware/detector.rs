use crate::config::HardwareConfig;
use serde::Serialize;
use tracing::{info, warn};

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub enum ComputeDevice {
    Cuda { name: String, total_vram_mb: u64 },
    IntelGpu { name: String },
    Cpu { available_cores: usize },
}

pub struct HardwareDetector;

impl HardwareDetector {
    pub fn probe_system(config: &HardwareConfig) -> ComputeDevice {
        let requested_accel = config.acceleration.to_lowercase();
        if requested_accel == "cpu" {
            info!("Hardware acceleration explicitly set to 'cpu'. Using CPU execution pool.");
            return ComputeDevice::Cpu {
                available_cores: num_cpus::get_physical(),
            };
        }

        #[cfg(target_os = "windows")]
        {
            if let Ok(device) = Self::probe_windows_wmi(config) {
                return device;
            }
        }

        warn!("No suitable hardware GPU detected. Falling back to multi-core CPU mode.");
        ComputeDevice::Cpu {
            available_cores: num_cpus::get_physical(),
        }
    }

    #[cfg(target_os = "windows")]
    fn probe_windows_wmi(config: &HardwareConfig) -> Result<ComputeDevice, Box<dyn std::error::Error>> {
        use std::collections::HashMap;
        use wmi::{COMLibrary, WMIConnection};

        let com_con = COMLibrary::new()?;
        let wmi_con = WMIConnection::new(com_con)?;

        let results: Vec<HashMap<String, serde_json::Value>> =
            wmi_con.raw_query("SELECT Name, PNPDeviceID, AdapterRAM FROM Win32_VideoController")?;

        let mut intel_adapter: Option<String> = None;

        for gpu in results {
            let name = gpu.get("Name").and_then(|v| v.as_str()).unwrap_or_default().to_string();
            let pnp = gpu.get("PNPDeviceID").and_then(|v| v.as_str()).unwrap_or_default().to_string();

            let adapter_ram_bytes = gpu.get("AdapterRAM").and_then(|v| v.as_u64()).unwrap_or(0);
            let vram_mb = if adapter_ram_bytes > 0 {
                adapter_ram_bytes / (1024 * 1024)
            } else {
                6144 // Default target for RTX 3060 Laptop GPU when WMI reports 32-bit uint overflow
            };

            // Detect Discrete NVIDIA GPU
            if pnp.contains("VEN_10DE") || name.to_lowercase().contains("nvidia") {
                if vram_mb >= config.min_vram_required_mb || adapter_ram_bytes == 0 {
                    info!(
                        "Accelerated Hardware Detected: {} (Estimated VRAM: {} MB)",
                        name, vram_mb
                    );
                    return Ok(ComputeDevice::Cuda {
                        name,
                        total_vram_mb: if vram_mb < 2048 { 6144 } else { vram_mb },
                    });
                } else {
                    warn!(
                        "NVIDIA GPU detected ({}) but available VRAM ({} MB) is below required minimum ({} MB).",
                        name, vram_mb, config.min_vram_required_mb
                    );
                }
            }

            // Detect Integrated Intel GPU
            if pnp.contains("VEN_8086") || name.to_lowercase().contains("intel") {
                intel_adapter = Some(name);
            }
        }

        if config.acceleration.to_lowercase() == "openvino" {
            if let Some(name) = intel_adapter {
                info!("OpenVINO Accelerated Adapter Detected: {}", name);
                return Ok(ComputeDevice::IntelGpu { name });
            }
        }

        if config.fallback_to_cpu {
            warn!("No dedicated NVIDIA CUDA GPU found meeting VRAM requirements. Falling back to multi-core CPU mode.");
            Ok(ComputeDevice::Cpu {
                available_cores: num_cpus::get_physical(),
            })
        } else {
            Err("No GPU acceleration available and CPU fallback is disabled.".into())
        }
    }
}
