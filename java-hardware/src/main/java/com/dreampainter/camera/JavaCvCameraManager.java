package com.dreampainter.camera;

import org.bytedeco.javacv.Frame;
import org.bytedeco.javacv.FrameGrabber;
import org.bytedeco.javacv.VideoInputFrameGrabber;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 使用 JavaCV 直接管理摄像头的最小实现。
 */
public class JavaCvCameraManager {

    private FrameGrabber currentGrabber;
    private Integer currentIndex;

    /**
     * 枚举本机摄像头设备。
     */
    public List<CameraDevice> listCameras() throws FrameGrabber.Exception {
        String[] descriptions = VideoInputFrameGrabber.getDeviceDescriptions();
        if (descriptions == null || descriptions.length == 0) {
            return Collections.emptyList();
        }
        List<CameraDevice> result = new ArrayList<>(descriptions.length);
        for (int i = 0; i < descriptions.length; i++) {
            result.add(new CameraDevice(i, descriptions[i]));
        }
        return result;
    }

    /**
     * 打开指定索引的摄像头。
     */
    public void openCamera(int index) throws FrameGrabber.Exception {
        if (currentGrabber != null) {
            if (currentIndex != null && currentIndex == index) {
                return;
            }
            closeCamera();
        }
        VideoInputFrameGrabber grabber = new VideoInputFrameGrabber(index);
        grabber.start();
        this.currentGrabber = grabber;
        this.currentIndex = index;
    }

    /**
     * 抓取一帧图像。
     */
    public Frame grabFrame() throws FrameGrabber.Exception {
        if (currentGrabber == null) {
            throw new IllegalStateException("Camera not opened. Call openCamera() first.");
        }
        return currentGrabber.grab();
    }

    /**
     * 关闭当前摄像头并释放资源。
     */
    public void closeCamera() throws FrameGrabber.Exception {
        if (currentGrabber != null) {
            try {
                currentGrabber.stop();
            } finally {
                try {
                    currentGrabber.close();
                } finally {
                    currentGrabber = null;
                    currentIndex = null;
                }
            }
        }
    }
}

