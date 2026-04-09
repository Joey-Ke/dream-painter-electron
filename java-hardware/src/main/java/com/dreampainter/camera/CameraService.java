package com.dreampainter.camera;

import org.bytedeco.javacv.Frame;
import org.bytedeco.javacv.FrameGrabber;

import java.util.List;

/**
 * 基于 JavaCvCameraManager 的简单服务封装，用于 demo。
 */
public class CameraService {

    private final JavaCvCameraManager cameraManager;

    public CameraService(JavaCvCameraManager cameraManager) {
        this.cameraManager = cameraManager;
    }

    /**
     * 枚举本机摄像头。
     */
    public List<CameraDevice> listCameras() throws FrameGrabber.Exception {
        return cameraManager.listCameras();
    }

    /**
     * 打开指定摄像头。
     */
    public void openCamera(int index) throws FrameGrabber.Exception {
        cameraManager.openCamera(index);
    }

    /**
     * 按设备名关键词优先选择摄像头，如果找不到则回退到指定索引。
     *
     * @param keyword      设备名关键词（忽略大小写），例如 "UGREEN"
     * @param fallbackIndex 回退使用的索引
     * @return 实际打开的摄像头索引，若没有任何摄像头则返回 -1
     */
    public int openCameraByKeywordOrIndex(String keyword, int fallbackIndex) throws FrameGrabber.Exception {
        List<CameraDevice> cameras = listCameras();
        if (cameras.isEmpty()) {
            System.out.println("No cameras available.");
            return -1;
        }

        Integer selectedIndex = null;

        if (keyword != null && !keyword.trim().isEmpty()) {
            String lowerKeyword = keyword.toLowerCase();
            for (CameraDevice device : cameras) {
                String name = device.getName();
                if (name != null && name.toLowerCase().contains(lowerKeyword)) {
                    selectedIndex = device.getIndex();
                    System.out.println("Selected camera by keyword \"" + keyword + "\": index=" +
                            device.getIndex() + ", name=" + device.getName());
                    break;
                }
            }
        }

        if (selectedIndex == null) {
            selectedIndex = fallbackIndex;
            System.out.println("No camera matched keyword \"" + keyword +
                    "\". Falling back to index " + fallbackIndex + ".");
        }

        openCamera(selectedIndex);
        return selectedIndex;
    }

    /**
     * 持续抓帧一段时间，用于验证采集是否正常。
     *
     * @param durationMillis 持续时间（毫秒）
     * @param intervalMillis 抓帧间隔（毫秒）
     */
    public void continuousCapture(long durationMillis, long intervalMillis) throws FrameGrabber.Exception {
        long end = System.currentTimeMillis() + durationMillis;
        int count = 0;
        while (System.currentTimeMillis() < end) {
            Frame frame = cameraManager.grabFrame();
            if (frame != null) {
                count++;
                System.out.println("Captured frame #" + count +
                        " (image=" + (frame.image != null) +
                        ", timestamp=" + frame.timestamp + ")");
            } else {
                System.out.println("Received null frame.");
            }
            try {
                Thread.sleep(intervalMillis);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        System.out.println("Continuous capture finished. Total frames: " + count);
    }

    /**
     * 关闭摄像头并释放资源。
     */
    public void closeCamera() throws FrameGrabber.Exception {
        cameraManager.closeCamera();
    }
}

