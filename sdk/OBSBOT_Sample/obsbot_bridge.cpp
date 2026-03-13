#include <iostream>
#include <vector>
#include <string>
#include <memory>
#include <cstring>
#include <algorithm>
#include "dev/devs.hpp"
#include "dev/dev.hpp"

extern "C" {

static std::shared_ptr<Device> g_current_device = nullptr;

bool obsbot_init() {
    Devices::get();
    return true;
}

int obsbot_get_device_count() {
    return (int)Devices::get().getDevNum();
}

bool obsbot_get_device_sn(int index, char* sn_out) {
    auto dev_list = Devices::get().getDevList();
    if (index < 0 || index >= dev_list.size()) return false;
    
    auto it = dev_list.begin();
    std::advance(it, index);
    std::string sn = (*it)->devSn();
    std::strncpy(sn_out, sn.c_str(), 32);
    return true;
}

bool obsbot_connect(const char* sn) {
    g_current_device = Devices::get().getDevBySn(sn);
    return g_current_device != nullptr;
}

void obsbot_disconnect() {
    g_current_device = nullptr;
}

bool obsbot_set_gimbal_speed(float pitch, float pan) {
    if (!g_current_device) return false;
    return g_current_device->aiSetGimbalSpeedCtrlR(pitch, pan) == RM_RET_OK;
}

bool obsbot_set_gimbal_angle(float pitch, float yaw) {
    if (!g_current_device) return false;
    return g_current_device->aiSetGimbalMotorAngleR(pitch, yaw) == RM_RET_OK;
}

bool obsbot_set_zoom(float zoom) {
    if (!g_current_device) return false;
    return g_current_device->cameraSetZoomAbsoluteR(zoom) == RM_RET_OK;
}

bool obsbot_set_ai_mode(int mode, int sub_mode) {
    if (!g_current_device) return false;
    return g_current_device->cameraSetAiModeU((Device::AiWorkModeType)mode, sub_mode) == RM_RET_OK;
}

bool obsbot_set_led(bool enabled) {
    if (!g_current_device) return false;
    return g_current_device->cameraSetLedCtrlU(enabled) == RM_RET_OK;
}

bool obsbot_get_gimbal_attitude(float* pitch, float* yaw, float* roll) {
    if (!g_current_device) return false;
    float xyz[3];
    if (g_current_device->gimbalGetAttitudeInfoR(xyz) == RM_RET_OK) {
        *roll = xyz[0];
        *pitch = xyz[1];
        *yaw = xyz[2];
        return true;
    }
    return false;
}

bool obsbot_set_track_target(float x_min, float y_min, float x_max, float y_max) {
    if (!g_current_device) return false;
    return g_current_device->aiSetSelectTargetByBox(x_min, y_min, x_max, y_max) == RM_RET_OK;
}

bool obsbot_reset_gimbal() {
    if (!g_current_device) return false;
    return g_current_device->gimbalRstPosR() == RM_RET_OK;
}

bool obsbot_set_privacy_mode(bool enabled) {
    if (!g_current_device) return false;
    Device::DevStatus status = enabled ? Device::DevStatusPrivacy : Device::DevStatusRun;
    return g_current_device->cameraSetDevRunStatusR(status) == RM_RET_OK;
}

}
