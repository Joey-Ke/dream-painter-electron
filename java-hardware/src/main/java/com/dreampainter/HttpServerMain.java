package com.dreampainter;

import com.dreampainter.camera.CameraDevice;
import com.dreampainter.camera.CameraService;
import com.dreampainter.camera.JavaCvCameraManager;
import com.dreampainter.capture.SnapshotService;
import com.dreampainter.processing.ImagePreprocessor;
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import org.bytedeco.javacv.Frame;
import org.bytedeco.javacv.FrameGrabber;
import org.bytedeco.javacv.Java2DFrameConverter;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.text.SimpleDateFormat;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 极简本地 HTTP 服务，用于 Electron 与 java-hardware 的联调。
 *
 * 暴露的接口（阶段四）：
 * - GET  /api/camera/devices
 * - POST /api/camera/open
 * - GET  /api/camera/preview/latest
 * - POST /api/capture/snapshot
 */
public class HttpServerMain {

    private static final int PORT = 18080;

    private static final String STATE_IDLE = "IDLE";
    private static final String STATE_PREVIEWING = "PREVIEWING";

    private final JavaCvCameraManager cameraManager = new JavaCvCameraManager();
    private final CameraService cameraService = new CameraService(cameraManager);
    private final SnapshotService snapshotService = new SnapshotService(cameraManager);
    private final ImagePreprocessor imagePreprocessor = new ImagePreprocessor();

    private final LatestFrameHolder latestFrameHolder = new LatestFrameHolder();

    private volatile String cameraState = STATE_IDLE;
    private Thread previewThread;
    private volatile boolean previewRunning = false;

    public static void main(String[] args) throws Exception {
        HttpServerMain app = new HttpServerMain();
        app.start();
    }

    private void start() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", PORT), 0);

        server.createContext("/api/camera/devices", new DevicesHandler());
        server.createContext("/api/camera/open", new OpenHandler());
        server.createContext("/api/camera/preview/latest", new PreviewLatestHandler());
        server.createContext("/api/capture/snapshot", new SnapshotHandler());

        ExecutorService executor = Executors.newCachedThreadPool();
        server.setExecutor(executor);

        server.start();
        System.out.println("java-hardware HTTP server started at http://127.0.0.1:" + PORT);
    }

    /**
     * 保存最新预览帧。
     */
    private static class LatestFrameHolder {
        volatile BufferedImage latestImage;
        volatile long capturedAtMillis;
    }

    private class DevicesHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendOptions(exchange);
                return;
            }
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendJson(exchange, 405, jsonError("INVALID_METHOD", "Only GET is allowed", null));
                return;
            }
            try {
                List<CameraDevice> devices = cameraService.listCameras();
                StringBuilder devicesJson = new StringBuilder();
                devicesJson.append("[");
                for (int i = 0; i < devices.size(); i++) {
                    CameraDevice d = devices.get(i);
                    if (i > 0) {
                        devicesJson.append(',');
                    }
                    devicesJson.append("{\"index\":")
                            .append(d.getIndex())
                            .append(",\"name\":\"")
                            .append(jsonEscape(d.getName()))
                            .append("\"}");
                }
                devicesJson.append("]");

                String dataJson = "{\"devices\":" + devicesJson + "}";
                String body = jsonSuccess(dataJson);
                sendJson(exchange, 200, body);
            } catch (FrameGrabber.Exception e) {
                e.printStackTrace();
                sendJson(exchange, 200, jsonError("CAMERA_ENUM_FAILED", e.getMessage(), null));
            }
        }
    }

    private class OpenHandler implements HttpHandler {
        private final Pattern indexPattern = Pattern.compile("\"deviceIndex\"\\s*:\\s*(\\d+)");

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendOptions(exchange);
                return;
            }
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendJson(exchange, 405, jsonError("INVALID_METHOD", "Only POST is allowed", null));
                return;
            }
            String body = readBody(exchange);
            Integer index = null;
            if (body != null && !body.trim().isEmpty()) {
                Matcher m = indexPattern.matcher(body);
                if (m.find()) {
                    index = Integer.parseInt(m.group(1));
                }
            }
            if (index == null) {
                sendJson(exchange, 200, jsonError("INVALID_REQUEST", "deviceIndex is required", null));
                return;
            }

            try {
                stopPreviewLoop();

                cameraService.openCamera(index);
                cameraState = STATE_PREVIEWING;
                startPreviewLoop();

                String deviceName = null;
                try {
                    List<CameraDevice> devices = cameraService.listCameras();
                    for (CameraDevice d : devices) {
                        if (d.getIndex() == index) {
                            deviceName = d.getName();
                            break;
                        }
                    }
                } catch (FrameGrabber.Exception ignore) {
                    // ignore, best-effort for name
                }

                StringBuilder openedDeviceJson = new StringBuilder();
                openedDeviceJson.append("{\"index\":").append(index);
                if (deviceName != null) {
                    openedDeviceJson.append(",\"name\":\"").append(jsonEscape(deviceName)).append("\"");
                }
                openedDeviceJson.append("}");

                String dataJson = "{\"state\":\"" + cameraState + "\",\"openedDevice\":" + openedDeviceJson + "}";
                sendJson(exchange, 200, jsonSuccess(dataJson));
            } catch (FrameGrabber.Exception e) {
                e.printStackTrace();
                cameraState = STATE_IDLE;
                sendJson(exchange, 200, jsonError("CAMERA_OPEN_FAILED", e.getMessage(), null));
            }
        }
    }

    private class PreviewLatestHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendOptions(exchange);
                return;
            }
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendJson(exchange, 405, jsonError("INVALID_METHOD", "Only GET is allowed", null));
                return;
            }
            if (!STATE_PREVIEWING.equals(cameraState)) {
                sendJson(exchange, 200, jsonError("CAMERA_NOT_OPEN", "Camera is not open.", "{\"state\":\"" + cameraState + "\"}"));
                return;
            }

            BufferedImage image = latestFrameHolder.latestImage;
            long ts = latestFrameHolder.capturedAtMillis;
            if (image == null) {
                sendJson(exchange, 200, jsonError("NO_LATEST_FRAME", "No preview frame available yet.", "{\"state\":\"" + cameraState + "\"}"));
                return;
            }

            try {
                String base64 = encodeImageToBase64(image, "jpeg");
                StringBuilder data = new StringBuilder();
                data.append("{\"state\":\"").append(cameraState).append("\",")
                        .append("\"capturedAt\":\"").append(formatTimestamp(ts)).append("\",")
                        .append("\"width\":").append(image.getWidth()).append(",")
                        .append("\"height\":").append(image.getHeight()).append(",")
                        .append("\"mimeType\":\"image/jpeg\",")
                        .append("\"imageBase64\":\"data:image/jpeg;base64,")
                        .append(base64)
                        .append("\"}");

                sendJson(exchange, 200, jsonSuccess(data.toString()));
            } catch (IOException e) {
                e.printStackTrace();
                sendJson(exchange, 200, jsonError("INTERNAL_ERROR", "Failed to encode latest frame.", null));
            }
        }
    }

    private class SnapshotHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendOptions(exchange);
                return;
            }
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendJson(exchange, 405, jsonError("INVALID_METHOD", "Only POST is allowed", null));
                return;
            }
            if (!STATE_PREVIEWING.equals(cameraState)) {
                sendJson(exchange, 200, jsonError("CAMERA_NOT_OPEN", "Camera is not open.", "{\"state\":\"" + cameraState + "\"}"));
                return;
            }

            // 当前版本忽略请求体参数（如 enableGrayscale），默认启用灰度化
            readBody(exchange); // consume body

            String tsToken = new SimpleDateFormat("yyyyMMdd-HHmmss-SSS").format(new Date());
            Path originalDir = Paths.get("snapshots", "original");
            Path processedDir = Paths.get("snapshots", "processed");
            java.io.File originalDirFile = originalDir.toFile();
            if (!originalDirFile.exists() && !originalDirFile.mkdirs() && !originalDirFile.exists()) {
                sendJson(exchange, 200, jsonError("PREPROCESS_FAILED", "Failed to create directory: " + originalDir, null));
                return;
            }
            java.io.File processedDirFile = processedDir.toFile();
            if (!processedDirFile.exists() && !processedDirFile.mkdirs() && !processedDirFile.exists()) {
                sendJson(exchange, 200, jsonError("PREPROCESS_FAILED", "Failed to create directory: " + processedDir, null));
                return;
            }

            Path originalPath = originalDir.resolve("snapshot-" + tsToken + ".png");
            Path processedPath = processedDir.resolve("snapshot-" + tsToken + ".png");

            try {
                java.io.File originalFile = snapshotService.takeSnapshot(originalPath);
                java.io.File processedFile = imagePreprocessor.preprocessAndSave(
                        originalFile,
                        processedPath,
                        true
                );

                StringBuilder data = new StringBuilder();
                data.append("{\"state\":\"").append(cameraState).append("\",")
                        .append("\"processedPath\":\"").append(jsonEscape(processedFile.getAbsolutePath())).append("\"}");

                sendJson(exchange, 200, jsonSuccess(data.toString()));
            } catch (FrameGrabber.Exception e) {
                e.printStackTrace();
                sendJson(exchange, 200, jsonError("SNAPSHOT_FAILED", e.getMessage(), null));
            } catch (IOException e) {
                e.printStackTrace();
                sendJson(exchange, 200, jsonError("PREPROCESS_FAILED", e.getMessage(), null));
            }
        }
    }

    /**
     * 启动预览抓帧循环，维护 latestFrame。
     */
    private synchronized void startPreviewLoop() {
        if (previewRunning && previewThread != null && previewThread.isAlive()) {
            return;
        }
        previewRunning = true;
        previewThread = new Thread(() -> {
            System.out.println("Preview loop started.");
            Java2DFrameConverter converter = new Java2DFrameConverter();
            while (previewRunning) {
                try {
                    Frame frame = cameraManager.grabFrame();
                    if (frame != null) {
                        BufferedImage img = converter.convert(frame);
                        if (img != null) {
                            latestFrameHolder.latestImage = img;
                            latestFrameHolder.capturedAtMillis = System.currentTimeMillis();
                        }
                    }
                    Thread.sleep(150);
                } catch (FrameGrabber.Exception e) {
                    e.printStackTrace();
                    // 出现错误时稍作等待，避免疯狂打日志
                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            converter.close();
            System.out.println("Preview loop stopped.");
        }, "camera-preview-loop");
        previewThread.setDaemon(true);
        previewThread.start();
    }

    private synchronized void stopPreviewLoop() {
        previewRunning = false;
        if (previewThread != null) {
            previewThread.interrupt();
            previewThread = null;
        }
        latestFrameHolder.latestImage = null;
        latestFrameHolder.capturedAtMillis = 0L;
    }

    // ========== 工具方法 ==========

    private static void sendJson(HttpExchange exchange, int statusCode, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        Headers headers = exchange.getResponseHeaders();
        headers.set("Content-Type", "application/json; charset=utf-8");
        headers.set("Access-Control-Allow-Origin", "*");
        headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        headers.set("Access-Control-Allow-Headers", "Content-Type");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void sendOptions(HttpExchange exchange) throws IOException {
        Headers headers = exchange.getResponseHeaders();
        headers.set("Access-Control-Allow-Origin", "*");
        headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        headers.set("Access-Control-Allow-Headers", "Content-Type");
        exchange.sendResponseHeaders(204, -1);
        exchange.close();
    }

    private static String readBody(HttpExchange exchange) throws IOException {
        try (InputStream is = exchange.getRequestBody()) {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            byte[] buf = new byte[1024];
            int len;
            while ((len = is.read(buf)) != -1) {
                baos.write(buf, 0, len);
            }
            return baos.toString(StandardCharsets.UTF_8.name());
        }
    }

    private static String jsonEscape(String s) {
        if (s == null) {
            return "";
        }
        return s
                .replace("\\", "\\\\")
                .replace("\"", "\\\"");
    }

    private static String jsonSuccess(String dataJson) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"success\":true,\"code\":\"OK\",\"message\":\"\",\"data\":");
        if (dataJson == null) {
            sb.append("null");
        } else {
            sb.append(dataJson);
        }
        sb.append("}");
        return sb.toString();
    }

    private static String jsonError(String code, String message, String dataJson) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"success\":false,\"code\":\"")
                .append(code)
                .append("\",\"message\":\"")
                .append(jsonEscape(message))
                .append("\",\"data\":");
        if (dataJson == null) {
            sb.append("null");
        } else {
            sb.append(dataJson);
        }
        sb.append("}");
        return sb.toString();
    }

    private static String encodeImageToBase64(BufferedImage image, String format) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        ImageIO.write(image, format, baos);
        byte[] bytes = baos.toByteArray();
        return Base64.getEncoder().encodeToString(bytes);
    }

    private static String formatTimestamp(long millis) {
        if (millis <= 0L) {
            return "";
        }
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX").format(new Date(millis));
    }
}

