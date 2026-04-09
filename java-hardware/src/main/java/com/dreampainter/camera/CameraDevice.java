package com.dreampainter.camera;

/**
 * 简单的摄像头描述对象，用于展示和选择设备。
 */
public class CameraDevice {

    private final int index;
    private final String name;

    public CameraDevice(int index, String name) {
        this.index = index;
        this.name = name;
    }

    public int getIndex() {
        return index;
    }

    public String getName() {
        return name;
    }

    @Override
    public String toString() {
        return "CameraDevice{" +
                "index=" + index +
                ", name='" + name + '\'' +
                '}';
    }
}

