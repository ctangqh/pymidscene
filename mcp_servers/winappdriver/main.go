// Package main provides an MCP (Model Context Protocol) Server for WinAppDriver.
// It exposes tools via SSE (Server-Sent Events) transport.
package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

const w3cElementKey = "element-6066-11e4-a52e-4f735466cecf"

// ==================== Config ====================

type Config struct {
	MCPHost             string
	MCPPort             int
	MCPLogVerbose       bool
	WinAppDriverHost    string
	WinAppDriverPort    int
	WinAppDriverURL     string
	WinAppDriverTimeout int
	AutoStart           bool
}

var cfg Config

func loadConfig() {
	configPaths := []string{"mcp.conf", "dist/mcp.conf", "./dist/mcp.conf"}
	for _, p := range configPaths {
		if data, err := os.ReadFile(p); err == nil {
			for _, line := range strings.Split(string(data), "\n") {
				line = strings.TrimSpace(line)
				if line == "" || strings.HasPrefix(line, "#") {
					continue
				}
				parts := strings.SplitN(line, "=", 2)
				if len(parts) == 2 {
					os.Setenv(strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1]))
				}
			}
			log.Printf("[INFO] Loaded config from: %s", p)
			break
		}
	}

	cfg.MCPHost = getEnv("MCP_HOST", "0.0.0.0")
	cfg.MCPPort = getEnvInt("MCP_PORT", 55001)
	cfg.MCPLogVerbose = getEnvBool("MCP_LOG_VERBOSE", false)
	cfg.WinAppDriverHost = getEnv("WINAPPDRIVER_HOST", "127.0.0.1")
	cfg.WinAppDriverPort = getEnvInt("WINAPPDRIVER_PORT", 4723)
	cfg.WinAppDriverTimeout = getEnvInt("WINAPPDRIVER_HTTP_TIMEOUT", 120)
	cfg.AutoStart = getEnvBool("WINAPPDRIVER_AUTO_START", false)
	cfg.WinAppDriverURL = fmt.Sprintf("http://%s:%d", cfg.WinAppDriverHost, cfg.WinAppDriverPort)
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		var i int
		fmt.Sscanf(v, "%d", &i)
		return i
	}
	return fallback
}

func getEnvBool(key string, fallback bool) bool {
	if v := strings.TrimSpace(strings.ToLower(os.Getenv(key))); v != "" {
		return v == "1" || v == "true" || v == "yes" || v == "on"
	}
	return fallback
}

func verboseLog(format string, args ...interface{}) {
	if cfg.MCPLogVerbose {
		log.Printf(format, args...)
	}
}

// ==================== WinAppDriver Client ====================

type WDClient struct {
	baseURL string
	timeout time.Duration
	session string
	mu      sync.RWMutex
	client  *http.Client
	proc    *exec.Cmd
}

type wdEnvelope struct {
	SessionID string          `json:"sessionId"`
	Status    int             `json:"status"`
	Value     json.RawMessage `json:"value"`
}

var wd *WDClient

func newWDClient() *WDClient {
	return &WDClient{
		baseURL: cfg.WinAppDriverURL,
		timeout: time.Duration(cfg.WinAppDriverTimeout) * time.Second,
		client:  &http.Client{Timeout: time.Duration(cfg.WinAppDriverTimeout) * time.Second},
	}
}

func (c *WDClient) setSession(id string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.session = id
}

func (c *WDClient) getSession() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.session
}

func (c *WDClient) startWinAppDriver() error {
	if c.proc != nil && c.proc.Process != nil {
		return nil
	}

	possiblePaths := []string{
		`C:\Program Files (x86)\Windows Application Driver\WinAppDriver.exe`,
		`C:\Program Files\Windows Application Driver\WinAppDriver.exe`,
		`WinAppDriver.exe`,
	}

	for _, path := range possiblePaths {
		cmd := exec.Command(path, cfg.WinAppDriverHost, fmt.Sprintf("%d", cfg.WinAppDriverPort))
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
		if err := cmd.Start(); err != nil {
			continue
		}
		c.proc = cmd
		time.Sleep(2 * time.Second)
		log.Printf("[INFO] Started WinAppDriver: %s", path)
		return nil
	}

	return fmt.Errorf("WinAppDriver not found; install it or add WinAppDriver.exe to PATH")
}

func (c *WDClient) stopWinAppDriver() {
	if c.proc == nil || c.proc.Process == nil {
		return
	}
	_ = c.proc.Process.Kill()
	_, _ = c.proc.Process.Wait()
	c.proc = nil
}

func (c *WDClient) ensureServiceStarted() error {
	if !cfg.AutoStart {
		return nil
	}
	if _, _, err := c.do("GET", "/status", nil); err == nil {
		return nil
	}
	return c.startWinAppDriver()
}

func (c *WDClient) do(method, path string, body interface{}) ([]byte, int, error) {
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}

	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, 0, err
		}
		bodyReader = strings.NewReader(string(data))
	}

	req, err := http.NewRequest(method, c.baseURL+path, bodyReader)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, resp.StatusCode, err
	}
	return bodyBytes, resp.StatusCode, nil
}

func (c *WDClient) resolvePath(path, sessionID string) (string, error) {
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	if sessionID == "" {
		sessionID = c.getSession()
	}
	if strings.Contains(path, ":sessionId") || strings.Contains(path, "{sessionId}") {
		if sessionID == "" {
			return "", fmt.Errorf("no active session")
		}
		path = strings.ReplaceAll(path, ":sessionId", sessionID)
		path = strings.ReplaceAll(path, "{sessionId}", sessionID)
	}
	return path, nil
}

func (c *WDClient) request(method, path string, body interface{}) (json.RawMessage, []byte, error) {
	return c.requestWithSession("", method, path, body)
}

func (c *WDClient) requestWithSession(sessionID, method, path string, body interface{}) (json.RawMessage, []byte, error) {
	resolvedPath, err := c.resolvePath(path, sessionID)
	if err != nil {
		verboseLog("[WD] %s %s resolve failed: %v", method, path, err)
		return nil, nil, err
	}
	start := time.Now()
	bodyBytes, statusCode, err := c.do(method, resolvedPath, body)
	if err != nil {
		verboseLog("[WD] %s %s request failed after %s: %v", method, resolvedPath, time.Since(start), err)
		return nil, bodyBytes, err
	}
	if statusCode < 200 || statusCode >= 300 {
		verboseLog("[WD] %s %s -> HTTP %d in %s body=%s", method, resolvedPath, statusCode, time.Since(start), previewString(string(bodyBytes), 300))
		return nil, bodyBytes, fmt.Errorf("WinAppDriver HTTP %d: %s", statusCode, strings.TrimSpace(string(bodyBytes)))
	}
	value, err := unwrapWebDriverValue(bodyBytes)
	if err != nil {
		verboseLog("[WD] %s %s unwrap failed in %s: %v body=%s", method, resolvedPath, time.Since(start), err, previewString(string(bodyBytes), 300))
		return nil, bodyBytes, err
	}
	verboseLog("[WD] %s %s -> HTTP %d in %s payload=%s value=%s", method, resolvedPath, statusCode, time.Since(start), summarizeForLog(body), previewString(prettyRawJSON(value), 300))
	return value, bodyBytes, nil
}

func unwrapWebDriverValue(body []byte) (json.RawMessage, error) {
	if len(strings.TrimSpace(string(body))) == 0 {
		return nil, nil
	}
	if !json.Valid(body) {
		return json.RawMessage(body), nil
	}

	var envelope map[string]json.RawMessage
	if err := json.Unmarshal(body, &envelope); err != nil {
		return json.RawMessage(body), nil
	}

	if rawStatus, ok := envelope["status"]; ok {
		var status int
		_ = json.Unmarshal(rawStatus, &status)
		if status != 0 {
			return nil, fmt.Errorf(extractWebDriverError(body))
		}
	}

	if rawValue, ok := envelope["value"]; ok {
		return rawValue, nil
	}
	return json.RawMessage(body), nil
}

func extractWebDriverError(body []byte) string {
	var resp struct {
		Value struct {
			Message string `json:"message"`
			Error   string `json:"error"`
		} `json:"value"`
	}
	if err := json.Unmarshal(body, &resp); err == nil {
		if resp.Value.Message != "" {
			if resp.Value.Error != "" {
				return fmt.Sprintf("%s: %s", resp.Value.Error, resp.Value.Message)
			}
			return resp.Value.Message
		}
	}
	return strings.TrimSpace(string(body))
}

func (c *WDClient) CreateSession(app, appArgs, platformName, deviceName string) (string, error) {
	if err := c.ensureServiceStarted(); err != nil {
		return "", err
	}

	capabilities := map[string]interface{}{
		"platformName": platformName,
		"deviceName":   deviceName,
		"app":          app,
	}
	if appArgs != "" {
		capabilities["appArguments"] = appArgs
	}

	payload := map[string]interface{}{
		"desiredCapabilities": capabilities,
	}

	body, code, err := c.do("POST", "/session", payload)
	if err != nil {
		return "", fmt.Errorf("create session failed: %w", err)
	}
	if code != 200 && code != 201 {
		return "", fmt.Errorf("create session HTTP %d: %s", code, strings.TrimSpace(string(body)))
	}

	var envelope wdEnvelope
	_ = json.Unmarshal(body, &envelope)

	sessionID := envelope.SessionID
	if sessionID == "" && len(envelope.Value) > 0 {
		var value struct {
			SessionID string `json:"sessionId"`
		}
		_ = json.Unmarshal(envelope.Value, &value)
		sessionID = value.SessionID
	}

	if sessionID == "" {
		return "", fmt.Errorf("create session succeeded but sessionId is missing: %s", strings.TrimSpace(string(body)))
	}

	c.setSession(sessionID)
	return sessionID, nil
}

func (c *WDClient) DeleteSession() error {
	sess := c.getSession()
	if sess == "" {
		return nil
	}
	if _, _, err := c.request("DELETE", "/session/:sessionId", nil); err != nil {
		return err
	}
	c.setSession("")
	return nil
}

func (c *WDClient) GetSessions() ([]string, error) {
	value, _, err := c.request("GET", "/sessions", nil)
	if err != nil {
		return nil, err
	}

	var ids []string
	if err := json.Unmarshal(value, &ids); err == nil && len(ids) > 0 {
		return ids, nil
	}

	var sessions []struct {
		ID        string `json:"id"`
		SessionID string `json:"sessionId"`
	}
	if err := json.Unmarshal(value, &sessions); err == nil {
		for _, session := range sessions {
			if session.SessionID != "" {
				ids = append(ids, session.SessionID)
			} else if session.ID != "" {
				ids = append(ids, session.ID)
			}
		}
	}
	return ids, nil
}

func (c *WDClient) GetStatus() (json.RawMessage, error) {
	value, raw, err := c.request("GET", "/status", nil)
	if err != nil {
		return nil, err
	}
	if len(value) == 0 {
		return json.RawMessage(raw), nil
	}
	return value, nil
}

func (c *WDClient) AppLaunch() error {
	_, _, err := c.request("POST", "/session/:sessionId/appium/app/launch", nil)
	return err
}

func (c *WDClient) AppClose() error {
	_, _, err := c.request("POST", "/session/:sessionId/appium/app/close", nil)
	return err
}

func (c *WDClient) NavigateBack() error {
	_, _, err := c.request("POST", "/session/:sessionId/back", nil)
	return err
}

func (c *WDClient) NavigateForward() error {
	_, _, err := c.request("POST", "/session/:sessionId/forward", nil)
	return err
}

func (c *WDClient) GetSource() (string, error) {
	value, _, err := c.request("GET", "/session/:sessionId/source", nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) GetTitle() (string, error) {
	value, _, err := c.request("GET", "/session/:sessionId/title", nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) GetLocation() (map[string]interface{}, error) {
	value, _, err := c.request("GET", "/session/:sessionId/location", nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) GetOrientation() (string, error) {
	value, _, err := c.request("GET", "/session/:sessionId/orientation", nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) SetTimeout(timeoutType string, ms int) error {
	_, _, err := c.request("POST", "/session/:sessionId/timeouts", map[string]interface{}{
		"type": timeoutType,
		"ms":   ms,
	})
	return err
}

func (c *WDClient) Screenshot() ([]byte, error) {
	value, _, err := c.request("GET", "/session/:sessionId/screenshot", nil)
	if err != nil {
		return nil, err
	}
	b64, err := parseJSONString(value)
	if err != nil {
		return nil, err
	}
	return base64.StdEncoding.DecodeString(b64)
}

func (c *WDClient) screenshotWithSource() ([]byte, string, error) {
	img, err := c.Screenshot()
	if err == nil {
		return img, "winappdriver", nil
	}
	if isNoSuchWindowErr(err) {
		handle, recoverErr := c.recoverCurrentWindow()
		if recoverErr == nil {
			log.Printf("[WARN] WinAppDriver screenshot window was closed, recovered handle=%s and retrying screenshot", handle)
			img, retryErr := c.Screenshot()
			if retryErr == nil {
				return img, "winappdriver_recovered_window", nil
			}
			err = fmt.Errorf("%v; retry after window recovery failed: %v", err, retryErr)
		} else {
			err = fmt.Errorf("%v; recover window failed: %v", err, recoverErr)
		}
	}

	verboseLog("[WD] primary screenshot failed, trying window capture fallback: %v", err)
	windowImg, windowErr := c.captureCurrentWindowScreenshot()
	if windowErr == nil {
		log.Printf("[WARN] WinAppDriver screenshot failed, using window capture fallback: %v", err)
		return windowImg, "window_fallback", nil
	}

	verboseLog("[WD] window capture fallback failed, trying desktop capture fallback: %v", windowErr)
	desktopImg, desktopErr := captureDesktopScreenshot()
	if desktopErr == nil {
		log.Printf("[WARN] WinAppDriver screenshot failed, using desktop capture fallback: %v; window fallback error: %v", err, windowErr)
		return desktopImg, "desktop_fallback", nil
	}

	return nil, "", fmt.Errorf("primary screenshot failed: %v; window fallback failed: %v; desktop fallback failed: %w", err, windowErr, desktopErr)
}

func (c *WDClient) ScreenshotWithFallback() ([]byte, error) {
	img, _, err := c.screenshotWithSource()
	return img, err
}

func (c *WDClient) captureCurrentWindowScreenshot() ([]byte, error) {
	if err := c.ensureCurrentWindow(); err != nil {
		return nil, err
	}
	position, err := c.GetWindowPosition("")
	if err != nil {
		return nil, fmt.Errorf("get window position failed: %w", err)
	}
	size, err := c.GetWindowSize("")
	if err != nil {
		return nil, fmt.Errorf("get window size failed: %w", err)
	}

	x, ok := mapInt(position, "x")
	if !ok {
		return nil, fmt.Errorf("window position missing x: %v", position)
	}
	y, ok := mapInt(position, "y")
	if !ok {
		return nil, fmt.Errorf("window position missing y: %v", position)
	}
	width, ok := mapInt(size, "width")
	if !ok {
		return nil, fmt.Errorf("window size missing width: %v", size)
	}
	height, ok := mapInt(size, "height")
	if !ok {
		return nil, fmt.Errorf("window size missing height: %v", size)
	}
	if width <= 0 || height <= 0 {
		return nil, fmt.Errorf("invalid window rect: x=%d y=%d width=%d height=%d", x, y, width, height)
	}

	return captureScreenRegion(x, y, width, height)
}

func captureDesktopScreenshot() ([]byte, error) {
	script := `
param([string]$OutputPath)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
$bmp.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
`
	return runPowerShellScreenshot(script)
}

func captureScreenRegion(x, y, width, height int) ([]byte, error) {
	script := fmt.Sprintf(`
param([string]$OutputPath)
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap(%d, %d)
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen(%d, %d, 0, 0, $bmp.Size)
$bmp.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
`, width, height, x, y)
	return runPowerShellScreenshot(script)
}

func runPowerShellScreenshot(script string) ([]byte, error) {
	tempDir, err := os.MkdirTemp("", "winappdriver-screenshot-*")
	if err != nil {
		return nil, fmt.Errorf("create temp screenshot dir failed: %w", err)
	}
	defer os.RemoveAll(tempDir)

	scriptPath := tempDir + `\capture.ps1`
	outputPath := tempDir + `\capture.png`
	if err := os.WriteFile(scriptPath, []byte(script), 0o600); err != nil {
		return nil, fmt.Errorf("write powershell screenshot script failed: %w", err)
	}

	cmd := exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath, "-OutputPath", outputPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("powershell screenshot failed: %v: %s", err, previewString(string(output), 300))
	}
	img, err := os.ReadFile(outputPath)
	if err != nil {
		return nil, fmt.Errorf("read powershell screenshot output failed: %w (stdout=%s)", err, previewString(string(output), 300))
	}
	if len(img) == 0 {
		return nil, fmt.Errorf("powershell screenshot output is empty")
	}
	return img, nil
}

func (c *WDClient) ensureCurrentWindow() error {
	_, err := c.GetWindowHandle()
	if err == nil {
		return nil
	}
	if !isNoSuchWindowErr(err) {
		return err
	}
	handle, recoverErr := c.recoverCurrentWindow()
	if recoverErr != nil {
		return fmt.Errorf("current window invalid: %v; recover window failed: %v", err, recoverErr)
	}
	log.Printf("[WARN] Recovered current window handle: %s", handle)
	return nil
}

func (c *WDClient) recoverCurrentWindow() (string, error) {
	handles, err := c.GetWindowHandles()
	if err != nil {
		return "", err
	}
	if len(handles) == 0 {
		return "", fmt.Errorf("no available window handles")
	}
	for i := len(handles) - 1; i >= 0; i-- {
		handle := strings.TrimSpace(handles[i])
		if handle == "" {
			continue
		}
		if err := c.SwitchWindow(handle); err == nil {
			return handle, nil
		}
	}
	return "", fmt.Errorf("failed to switch to any available window handle: %v", handles)
}

func isNoSuchWindowErr(err error) bool {
	if err == nil {
		return false
	}
	return strings.Contains(strings.ToLower(err.Error()), "no such window")
}

func (c *WDClient) FindElement(strategy, selector string) (string, error) {
	value, _, err := c.request("POST", "/session/:sessionId/element", map[string]string{
		"using": strategy,
		"value": selector,
	})
	if err != nil {
		return "", err
	}
	elementID := extractElementID(value)
	if elementID == "" {
		return "", fmt.Errorf("element id not found in response: %s", prettyRawJSON(value))
	}
	return elementID, nil
}

func (c *WDClient) FindElements(strategy, selector string) ([]string, error) {
	value, _, err := c.request("POST", "/session/:sessionId/elements", map[string]string{
		"using": strategy,
		"value": selector,
	})
	if err != nil {
		return nil, err
	}
	return extractElementIDs(value), nil
}

func (c *WDClient) GetActiveElement() (string, error) {
	value, _, err := c.request("POST", "/session/:sessionId/element/active", nil)
	if err != nil {
		return "", err
	}
	elementID := extractElementID(value)
	if elementID == "" {
		return "", fmt.Errorf("active element id not found in response: %s", prettyRawJSON(value))
	}
	return elementID, nil
}

func (c *WDClient) FindElementFromElement(parentID, strategy, selector string) (string, error) {
	value, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/element/%s/element", parentID), map[string]string{
		"using": strategy,
		"value": selector,
	})
	if err != nil {
		return "", err
	}
	elementID := extractElementID(value)
	if elementID == "" {
		return "", fmt.Errorf("child element id not found in response: %s", prettyRawJSON(value))
	}
	return elementID, nil
}

func (c *WDClient) FindElementsFromElement(parentID, strategy, selector string) ([]string, error) {
	value, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/element/%s/elements", parentID), map[string]string{
		"using": strategy,
		"value": selector,
	})
	if err != nil {
		return nil, err
	}
	return extractElementIDs(value), nil
}

func (c *WDClient) ClickElement(elementID string) error {
	_, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/element/%s/click", elementID), nil)
	return err
}

func (c *WDClient) ClearElement(elementID string) error {
	_, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/element/%s/clear", elementID), nil)
	return err
}

func (c *WDClient) SendKeysToElement(elementID, text string) error {
	_, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/element/%s/value", elementID), map[string]interface{}{
		"text":  text,
		"value": stringToKeyValues(text),
	})
	return err
}

func (c *WDClient) GetElementAttribute(elementID, name string) (string, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/attribute/%s", elementID, name), nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) GetElementText(elementID string) (string, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/text", elementID), nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) GetElementName(elementID string) (string, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/name", elementID), nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) IsElementDisplayed(elementID string) (bool, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/displayed", elementID), nil)
	if err != nil {
		return false, err
	}
	return parseJSONBool(value)
}

func (c *WDClient) IsElementEnabled(elementID string) (bool, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/enabled", elementID), nil)
	if err != nil {
		return false, err
	}
	return parseJSONBool(value)
}

func (c *WDClient) IsElementSelected(elementID string) (bool, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/selected", elementID), nil)
	if err != nil {
		return false, err
	}
	return parseJSONBool(value)
}

func (c *WDClient) GetElementLocation(elementID string) (map[string]interface{}, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/location", elementID), nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) GetElementLocationInView(elementID string) (map[string]interface{}, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/location_in_view", elementID), nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) GetElementSize(elementID string) (map[string]interface{}, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/size", elementID), nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) GetElementScreenshot(elementID string) ([]byte, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/screenshot", elementID), nil)
	if err != nil {
		return nil, err
	}
	b64, err := parseJSONString(value)
	if err != nil {
		return nil, err
	}
	return base64.StdEncoding.DecodeString(b64)
}

func (c *WDClient) ElementsEqual(elementID, otherElementID string) (bool, error) {
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/element/%s/equals?other=%s", elementID, otherElementID), nil)
	if err != nil {
		return false, err
	}
	return parseJSONBool(value)
}

func (c *WDClient) SendKeys(keys string) error {
	_, _, err := c.request("POST", "/session/:sessionId/keys", map[string]interface{}{
		"text":  keys,
		"value": stringToKeyValues(keys),
	})
	return err
}

func (c *WDClient) MouseMove(x, y int, elementID string) error {
	payload := map[string]interface{}{
		"xoffset": x,
		"yoffset": y,
	}
	if elementID != "" {
		payload["element"] = elementID
	}
	_, _, err := c.request("POST", "/session/:sessionId/moveto", payload)
	return err
}

func (c *WDClient) MouseClick(button int) error {
	_, _, err := c.request("POST", "/session/:sessionId/click", map[string]int{"button": button})
	return err
}

func (c *WDClient) MouseDoubleClick() error {
	_, _, err := c.request("POST", "/session/:sessionId/doubleclick", nil)
	return err
}

func (c *WDClient) MouseButtonDown(button int) error {
	_, _, err := c.request("POST", "/session/:sessionId/buttondown", map[string]int{"button": button})
	return err
}

func (c *WDClient) MouseButtonUp(button int) error {
	_, _, err := c.request("POST", "/session/:sessionId/buttonup", map[string]int{"button": button})
	return err
}

func (c *WDClient) GetWindowHandle() (string, error) {
	value, _, err := c.request("GET", "/session/:sessionId/window_handle", nil)
	if err != nil {
		return "", err
	}
	return parseJSONString(value)
}

func (c *WDClient) GetWindowHandles() ([]string, error) {
	value, _, err := c.request("GET", "/session/:sessionId/window_handles", nil)
	if err != nil {
		return nil, err
	}
	var handles []string
	if err := json.Unmarshal(value, &handles); err != nil {
		return nil, err
	}
	return handles, nil
}

func (c *WDClient) SwitchWindow(handle string) error {
	_, _, err := c.request("POST", "/session/:sessionId/window", map[string]string{"name": handle})
	return err
}

func (c *WDClient) CloseWindow() error {
	_, _, err := c.request("DELETE", "/session/:sessionId/window", nil)
	return err
}

func (c *WDClient) SetWindowSize(handle string, width, height int) error {
	path := "/session/:sessionId/window/size"
	if handle != "" {
		path = fmt.Sprintf("/session/:sessionId/window/%s/size", handle)
	}
	_, _, err := c.request("POST", path, map[string]int{
		"width":  width,
		"height": height,
	})
	return err
}

func (c *WDClient) GetWindowSize(handle string) (map[string]interface{}, error) {
	path := "/session/:sessionId/window/size"
	if handle != "" {
		path = fmt.Sprintf("/session/:sessionId/window/%s/size", handle)
	}
	value, _, err := c.request("GET", path, nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) SetWindowPosition(handle string, x, y int) error {
	if handle == "" {
		var err error
		handle, err = c.GetWindowHandle()
		if err != nil {
			return err
		}
	}
	_, _, err := c.request("POST", fmt.Sprintf("/session/:sessionId/window/%s/position", handle), map[string]int{
		"x": x,
		"y": y,
	})
	return err
}

func (c *WDClient) GetWindowPosition(handle string) (map[string]interface{}, error) {
	if handle == "" {
		var err error
		handle, err = c.GetWindowHandle()
		if err != nil {
			return nil, err
		}
	}
	value, _, err := c.request("GET", fmt.Sprintf("/session/:sessionId/window/%s/position", handle), nil)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(value)
}

func (c *WDClient) MaximizeWindow(handle string) error {
	path := "/session/:sessionId/window/maximize"
	if handle != "" {
		path = fmt.Sprintf("/session/:sessionId/window/%s/maximize", handle)
	}
	_, _, err := c.request("POST", path, nil)
	return err
}

func (c *WDClient) TouchClick(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/click", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchDoubleClick(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/doubleclick", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchLongClick(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/longclick", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchDown(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/down", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchMove(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/move", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchUp(x, y int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/up", map[string]int{"x": x, "y": y})
	return err
}

func (c *WDClient) TouchScroll(x, y, xoffset, yoffset int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/scroll", map[string]int{
		"x":       x,
		"y":       y,
		"xoffset": xoffset,
		"yoffset": yoffset,
	})
	return err
}

func (c *WDClient) TouchFlick(xspeed, yspeed int) error {
	_, _, err := c.request("POST", "/session/:sessionId/touch/flick", map[string]int{
		"xspeed": xspeed,
		"yspeed": yspeed,
	})
	return err
}

func (c *WDClient) RawRequest(sessionID, method, path string, payload interface{}) (json.RawMessage, []byte, error) {
	return c.requestWithSession(sessionID, method, path, payload)
}

// ==================== MCP Protocol Types ====================

type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      interface{}     `json:"id,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string        `json:"jsonrpc"`
	Result  interface{}   `json:"result,omitempty"`
	Error   *JSONRPCError `json:"error,omitempty"`
	ID      interface{}   `json:"id,omitempty"`
}

type JSONRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type MCPInitializeResult struct {
	ProtocolVersion string                 `json:"protocolVersion"`
	Capabilities    map[string]interface{} `json:"capabilities"`
	ServerInfo      map[string]interface{} `json:"serverInfo"`
}

type ToolCallParams struct {
	Name      string                 `json:"name"`
	Arguments map[string]interface{} `json:"arguments,omitempty"`
}

type ToolResult struct {
	Content []ContentBlock `json:"content"`
	IsError bool           `json:"isError,omitempty"`
}

type ContentBlock struct {
	Type     string `json:"type"`
	Text     string `json:"text,omitempty"`
	Data     string `json:"data,omitempty"`
	MimeType string `json:"mimeType,omitempty"`
}

type ToolDefinition struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	InputSchema map[string]interface{} `json:"inputSchema"`
	Handler     ToolHandler            `json:"-"`
}

// ==================== MCP Server ====================

type MCPServer struct {
	tools      map[string]ToolDefinition
	sessions   map[string]chan string
	sessionsMu sync.RWMutex
	httpAddr   string
}

type ToolHandler func(args map[string]interface{}) (interface{}, error)

func NewMCPServer(name, version, description string) *MCPServer {
	return &MCPServer{
		tools:    make(map[string]ToolDefinition),
		sessions: make(map[string]chan string),
	}
}

func (s *MCPServer) AddTool(name, description string, handler ToolHandler) {
	s.AddToolWithSchema(name, description, permissiveSchema(), handler)
}

func (s *MCPServer) AddToolWithSchema(name, description string, inputSchema map[string]interface{}, handler ToolHandler) {
	s.tools[name] = ToolDefinition{
		Name:        name,
		Description: description,
		InputSchema: inputSchema,
		Handler:     handler,
	}
	log.Printf("[INFO] Registered tool: %s", name)
}

func (s *MCPServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Path {
	case "/sse":
		s.handleSSE(w, r)
	case "/messages":
		s.handleMessage(w, r)
	case "/":
		s.handleRoot(w, r)
	default:
		http.NotFound(w, r)
	}
}

func (s *MCPServer) handleRoot(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"name":        "WinAppDriver MCP Server",
		"version":     "1.1.0",
		"description": "MCP Server for Windows App Driver",
		"tools":       s.tools,
	})
}

func (s *MCPServer) handleSSE(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "SSE not supported", http.StatusInternalServerError)
		return
	}

	sessionID := fmt.Sprintf("%d", time.Now().UnixNano())
	eventChan := make(chan string, 100)
	s.sessionsMu.Lock()
	s.sessions[sessionID] = eventChan
	s.sessionsMu.Unlock()
	log.Printf("[INFO] [MCP] SSE connected session=%s remote=%s", sessionID, r.RemoteAddr)

	fmt.Fprintf(w, "event: endpoint\ndata: /messages?session_id=%s\n\n", sessionID)
	flusher.Flush()

	heartbeat := time.NewTicker(15 * time.Second)
	defer func() {
		heartbeat.Stop()
		s.sessionsMu.Lock()
		delete(s.sessions, sessionID)
		s.sessionsMu.Unlock()
		close(eventChan)
		log.Printf("[INFO] [MCP] SSE disconnected session=%s remote=%s", sessionID, r.RemoteAddr)
	}()

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				return
			}
			fmt.Fprintf(w, "event: message\ndata: %s\n\n", event)
			flusher.Flush()
		case <-heartbeat.C:
			fmt.Fprintf(w, ": heartbeat\n\n")
			flusher.Flush()
		case <-r.Context().Done():
			return
		}
	}
}

func (s *MCPServer) handleMessage(w http.ResponseWriter, r *http.Request) {
	sessionID := r.URL.Query().Get("session_id")
	if sessionID == "" {
		http.Error(w, "session_id is required", http.StatusBadRequest)
		return
	}

	var req JSONRPCRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("[WARN] [MCP] session=%s parse error from %s: %v", sessionID, r.RemoteAddr, err)
		http.Error(w, "Parse error", http.StatusBadRequest)
		return
	}
	log.Printf("[INFO] [MCP] <- session=%s method=%s id=%v params=%s", sessionID, req.Method, req.ID, previewString(string(req.Params), 500))

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusAccepted)
	_, _ = w.Write([]byte("Accepted"))

	switch req.Method {
	case "initialize":
		result := MCPInitializeResult{
			ProtocolVersion: "2024-11-05",
			Capabilities: map[string]interface{}{
				"tools": map[string]interface{}{
					"listChanged": false,
				},
			},
			ServerInfo: map[string]interface{}{
				"name":    "WinAppDriver",
				"version": "1.1.0",
			},
		}
		log.Printf("[INFO] [MCP] initialize session=%s client_id=%v", sessionID, req.ID)
		s.sendSessionResponse(sessionID, req.ID, result)

	case "tools/list":
		toolsList := make([]ToolDefinition, 0, len(s.tools))
		for _, tool := range s.tools {
			toolsList = append(toolsList, ToolDefinition{
				Name:        tool.Name,
				Description: tool.Description,
				InputSchema: tool.InputSchema,
			})
		}
		log.Printf("[INFO] [MCP] tools/list session=%s tool_count=%d", sessionID, len(toolsList))
		s.sendSessionResponse(sessionID, req.ID, map[string]interface{}{"tools": toolsList})

	case "tools/call":
		var params ToolCallParams
		if req.Params != nil {
			_ = json.Unmarshal(req.Params, &params)
		}

		tool, ok := s.tools[params.Name]
		if !ok {
			log.Printf("[WARN] [MCP] tool missing session=%s name=%s", sessionID, params.Name)
			s.sendSessionError(sessionID, req.ID, -32602, fmt.Sprintf("Unknown tool: %s", params.Name))
			return
		}

		start := time.Now()
		log.Printf("[INFO] [MCP] tool start session=%s name=%s args=%s", sessionID, params.Name, summarizeForLog(params.Arguments))
		result, err := tool.Handler(params.Arguments)
		if err != nil {
			log.Printf("[ERROR] [MCP] tool error session=%s name=%s duration=%s err=%v", sessionID, params.Name, time.Since(start), err)
			s.sendSessionResponse(sessionID, req.ID, errorResult(err))
			return
		}
		if tr, ok := result.(ToolResult); ok {
			log.Printf("[INFO] [MCP] tool done session=%s name=%s duration=%s is_error=%t result=%s", sessionID, params.Name, time.Since(start), tr.IsError, summarizeToolResult(tr))
			s.sendSessionResponse(sessionID, req.ID, tr)
		} else {
			log.Printf("[INFO] [MCP] tool done session=%s name=%s duration=%s result=%s", sessionID, params.Name, time.Since(start), summarizeForLog(result))
			s.sendSessionResponse(sessionID, req.ID, result)
		}

	default:
		log.Printf("[INFO] [MCP] unsupported method session=%s method=%s id=%v", sessionID, req.Method, req.ID)
		if req.ID != nil {
			s.sendSessionResponse(sessionID, req.ID, nil)
		}
	}
}

func (s *MCPServer) sendSessionResponse(sessionID string, id interface{}, result interface{}) {
	resp := JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Result:  result,
	}
	log.Printf("[INFO] [MCP] -> session=%s id=%v result=%s", sessionID, id, summarizeForLog(result))
	s.enqueueSessionMessage(sessionID, resp)
}

func (s *MCPServer) sendSessionError(sessionID string, id interface{}, code int, message string) {
	resp := JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &JSONRPCError{Code: code, Message: message},
	}
	log.Printf("[WARN] [MCP] -> session=%s id=%v error_code=%d message=%s", sessionID, id, code, previewString(message, 300))
	s.enqueueSessionMessage(sessionID, resp)
}

func (s *MCPServer) enqueueSessionMessage(sessionID string, payload interface{}) {
	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[ERROR] marshal session message failed: %v", err)
		return
	}

	s.sessionsMu.RLock()
	eventChan, ok := s.sessions[sessionID]
	s.sessionsMu.RUnlock()
	if !ok {
		log.Printf("[WARN] session not found for response: %s", sessionID)
		return
	}

	select {
	case eventChan <- string(data):
	default:
		log.Printf("[WARN] session event queue full: %s", sessionID)
	}
}

// ==================== Tool Handlers ====================

func toolCreateSession(args map[string]interface{}) (interface{}, error) {
	app := requireString(args, "app")
	appArgs := getString(args, "app_args")
	platformName := getStringWithDefault(args, "platform_name", "Windows")
	deviceName := getStringWithDefault(args, "device_name", "WindowsPC")

	sessID, err := wd.CreateSession(app, appArgs, platformName, deviceName)
	if err != nil {
		return errorResult(fmt.Errorf("create session failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Session created: %s\nApp: %s", sessID, app)), nil
}

func toolDeleteSession(args map[string]interface{}) (interface{}, error) {
	if err := wd.DeleteSession(); err != nil {
		return errorResult(fmt.Errorf("delete session failed: %w", err)), nil
	}
	return textResult("Session closed."), nil
}

func toolGetSessions(args map[string]interface{}) (interface{}, error) {
	sessions, err := wd.GetSessions()
	if err != nil {
		return errorResult(fmt.Errorf("get sessions failed: %w", err)), nil
	}
	return textResult(prettyJSON(map[string]interface{}{
		"count":    len(sessions),
		"sessions": sessions,
	})), nil
}

func toolGetStatus(args map[string]interface{}) (interface{}, error) {
	status, err := wd.GetStatus()
	if err != nil {
		return errorResult(fmt.Errorf("get status failed: %w", err)), nil
	}
	return textResult(prettyRawJSON(status)), nil
}

func toolSetTimeout(args map[string]interface{}) (interface{}, error) {
	timeoutType := requireString(args, "timeout_type")
	ms := getInt(args, "ms")
	if err := wd.SetTimeout(timeoutType, ms); err != nil {
		return errorResult(fmt.Errorf("set timeout failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Timeout set: %s = %dms", timeoutType, ms)), nil
}

func toolAppLaunch(args map[string]interface{}) (interface{}, error) {
	if err := wd.AppLaunch(); err != nil {
		return errorResult(fmt.Errorf("app launch failed: %w", err)), nil
	}
	return textResult("App launched."), nil
}

func toolAppClose(args map[string]interface{}) (interface{}, error) {
	if err := wd.AppClose(); err != nil {
		return errorResult(fmt.Errorf("app close failed: %w", err)), nil
	}
	return textResult("App closed."), nil
}

func toolNavigateBack(args map[string]interface{}) (interface{}, error) {
	if err := wd.NavigateBack(); err != nil {
		return errorResult(fmt.Errorf("navigate back failed: %w", err)), nil
	}
	return textResult("Navigated back."), nil
}

func toolNavigateForward(args map[string]interface{}) (interface{}, error) {
	if err := wd.NavigateForward(); err != nil {
		return errorResult(fmt.Errorf("navigate forward failed: %w", err)), nil
	}
	return textResult("Navigated forward."), nil
}

func toolGetTitle(args map[string]interface{}) (interface{}, error) {
	title, err := wd.GetTitle()
	if err != nil {
		return errorResult(fmt.Errorf("get title failed: %w", err)), nil
	}
	return textResult(title), nil
}

func toolGetLocation(args map[string]interface{}) (interface{}, error) {
	location, err := wd.GetLocation()
	if err != nil {
		return errorResult(fmt.Errorf("get location failed: %w", err)), nil
	}
	return textResult(prettyJSON(location)), nil
}

func toolGetOrientation(args map[string]interface{}) (interface{}, error) {
	orientation, err := wd.GetOrientation()
	if err != nil {
		return errorResult(fmt.Errorf("get orientation failed: %w", err)), nil
	}
	return textResult(orientation), nil
}

func toolGetScreenshot(args map[string]interface{}) (interface{}, error) {
	img, source, err := wd.screenshotWithSource()
	if err != nil {
		return errorResult(fmt.Errorf("screenshot failed: %w", err)), nil
	}
	return ToolResult{
		Content: []ContentBlock{
			{Type: "image", Data: base64.StdEncoding.EncodeToString(img), MimeType: "image/png"},
			{Type: "text", Text: fmt.Sprintf("screenshot_source=%s", source)},
		},
	}, nil
}

func toolGetPageSource(args map[string]interface{}) (interface{}, error) {
	src, err := wd.GetSource()
	if err != nil {
		return errorResult(fmt.Errorf("get source failed: %w", err)), nil
	}
	return textResult(src), nil
}

func toolFindElement(args map[string]interface{}) (interface{}, error) {
	using := getStringWithDefault(args, "using", "accessibility id")
	selector := requireString(args, "selector")
	elementID, err := wd.FindElement(using, selector)
	if err != nil {
		return errorResult(fmt.Errorf("find element failed: %w", err)), nil
	}
	return textResult(elementID), nil
}

func toolFindElements(args map[string]interface{}) (interface{}, error) {
	using := getStringWithDefault(args, "using", "accessibility id")
	selector := requireString(args, "selector")
	elementIDs, err := wd.FindElements(using, selector)
	if err != nil {
		return errorResult(fmt.Errorf("find elements failed: %w", err)), nil
	}
	return textResult(prettyJSON(elementIDs)), nil
}

func toolFindElementFromElement(args map[string]interface{}) (interface{}, error) {
	parentID := getString(args, "parent_element_id")
	if parentID == "" {
		parentID = getString(args, "element_id")
	}
	using := getStringWithDefault(args, "using", "accessibility id")
	selector := requireString(args, "selector")
	elementID, err := wd.FindElementFromElement(parentID, using, selector)
	if err != nil {
		return errorResult(fmt.Errorf("find element from element failed: %w", err)), nil
	}
	return textResult(elementID), nil
}

func toolFindElementsFromElement(args map[string]interface{}) (interface{}, error) {
	parentID := getString(args, "parent_element_id")
	if parentID == "" {
		parentID = getString(args, "element_id")
	}
	using := getStringWithDefault(args, "using", "accessibility id")
	selector := requireString(args, "selector")
	elementIDs, err := wd.FindElementsFromElement(parentID, using, selector)
	if err != nil {
		return errorResult(fmt.Errorf("find elements from element failed: %w", err)), nil
	}
	return textResult(prettyJSON(elementIDs)), nil
}

func toolGetActiveElement(args map[string]interface{}) (interface{}, error) {
	elementID, err := wd.GetActiveElement()
	if err != nil {
		return errorResult(fmt.Errorf("get active element failed: %w", err)), nil
	}
	return textResult(elementID), nil
}

func toolClickElement(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	if err := wd.ClickElement(elementID); err != nil {
		return errorResult(fmt.Errorf("click element failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Clicked element: %s", elementID)), nil
}

func toolClearElement(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	if err := wd.ClearElement(elementID); err != nil {
		return errorResult(fmt.Errorf("clear element failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Cleared element: %s", elementID)), nil
}

func toolSendKeysToElement(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	text := getString(args, "text")
	if text == "" {
		text = getString(args, "keys")
	}
	if err := wd.SendKeysToElement(elementID, text); err != nil {
		return errorResult(fmt.Errorf("send keys to element failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Sent text to element: %s", elementID)), nil
}

func toolGetElementText(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.GetElementText(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element text failed: %w", err)), nil
	}
	return textResult(value), nil
}

func toolGetElementAttribute(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	name := requireString(args, "name")
	value, err := wd.GetElementAttribute(elementID, name)
	if err != nil {
		return errorResult(fmt.Errorf("get element attribute failed: %w", err)), nil
	}
	return textResult(value), nil
}

func toolGetElementName(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.GetElementName(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element name failed: %w", err)), nil
	}
	return textResult(value), nil
}

func toolIsElementDisplayed(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.IsElementDisplayed(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("is element displayed failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("%t", value)), nil
}

func toolIsElementEnabled(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.IsElementEnabled(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("is element enabled failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("%t", value)), nil
}

func toolIsElementSelected(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.IsElementSelected(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("is element selected failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("%t", value)), nil
}

func toolGetElementLocation(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.GetElementLocation(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element location failed: %w", err)), nil
	}
	return textResult(prettyJSON(value)), nil
}

func toolGetElementLocationInView(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.GetElementLocationInView(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element location in view failed: %w", err)), nil
	}
	return textResult(prettyJSON(value)), nil
}

func toolGetElementSize(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	value, err := wd.GetElementSize(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element size failed: %w", err)), nil
	}
	return textResult(prettyJSON(value)), nil
}

func toolGetElementScreenshot(args map[string]interface{}) (interface{}, error) {
	elementID, err := resolveElementID(args)
	if err != nil {
		return errorResult(err), nil
	}
	img, err := wd.GetElementScreenshot(elementID)
	if err != nil {
		return errorResult(fmt.Errorf("get element screenshot failed: %w", err)), nil
	}
	return ToolResult{
		Content: []ContentBlock{{Type: "image", Data: base64.StdEncoding.EncodeToString(img), MimeType: "image/png"}},
	}, nil
}

func toolCompareElements(args map[string]interface{}) (interface{}, error) {
	elementID := requireString(args, "element_id")
	otherElementID := requireString(args, "other_element_id")
	equal, err := wd.ElementsEqual(elementID, otherElementID)
	if err != nil {
		return errorResult(fmt.Errorf("compare elements failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("%t", equal)), nil
}

func toolMouseMove(args map[string]interface{}) (interface{}, error) {
	x := getInt(args, "x")
	y := getInt(args, "y")
	elementID := getString(args, "element_id")
	if elementID == "" && getString(args, "selector") != "" {
		var err error
		elementID, err = resolveElementID(args)
		if err != nil {
			return errorResult(err), nil
		}
	}
	if err := wd.MouseMove(x, y, elementID); err != nil {
		return errorResult(fmt.Errorf("mouse move failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Mouse moved: x=%d y=%d element=%s", x, y, elementID)), nil
}

func toolMouseClick(args map[string]interface{}) (interface{}, error) {
	if getString(args, "selector") != "" || hasKey(args, "x") || hasKey(args, "y") {
		if _, err := toolMouseMove(args); err != nil {
			return errorResult(err), nil
		}
	}
	button := parseMouseButton(getStringWithDefault(args, "button", "left"))
	if err := wd.MouseClick(button); err != nil {
		return errorResult(fmt.Errorf("mouse click failed: %w", err)), nil
	}
	return textResult("Mouse clicked."), nil
}

func toolMouseDoubleClick(args map[string]interface{}) (interface{}, error) {
	if getString(args, "selector") != "" || hasKey(args, "x") || hasKey(args, "y") {
		if _, err := toolMouseMove(args); err != nil {
			return errorResult(err), nil
		}
	}
	if err := wd.MouseDoubleClick(); err != nil {
		return errorResult(fmt.Errorf("mouse double click failed: %w", err)), nil
	}
	return textResult("Mouse double clicked."), nil
}

func toolMouseButtonDown(args map[string]interface{}) (interface{}, error) {
	if getString(args, "selector") != "" || hasKey(args, "x") || hasKey(args, "y") {
		if _, err := toolMouseMove(args); err != nil {
			return errorResult(err), nil
		}
	}
	button := parseMouseButton(getStringWithDefault(args, "button", "left"))
	if err := wd.MouseButtonDown(button); err != nil {
		return errorResult(fmt.Errorf("mouse button down failed: %w", err)), nil
	}
	return textResult("Mouse button down."), nil
}

func toolMouseButtonUp(args map[string]interface{}) (interface{}, error) {
	if getString(args, "selector") != "" || hasKey(args, "x") || hasKey(args, "y") {
		if _, err := toolMouseMove(args); err != nil {
			return errorResult(err), nil
		}
	}
	button := parseMouseButton(getStringWithDefault(args, "button", "left"))
	if err := wd.MouseButtonUp(button); err != nil {
		return errorResult(fmt.Errorf("mouse button up failed: %w", err)), nil
	}
	return textResult("Mouse button up."), nil
}

func toolSendKeys(args map[string]interface{}) (interface{}, error) {
	keys := getString(args, "keys")
	if keys == "" {
		keys = getString(args, "text")
	}
	if selector := getString(args, "selector"); selector != "" || getString(args, "element_id") != "" {
		return toolSendKeysToElement(args)
	}
	if err := wd.SendKeys(keys); err != nil {
		return errorResult(fmt.Errorf("send keys failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Sent keys: %s", keys)), nil
}

func toolPressKeys(args map[string]interface{}) (interface{}, error) {
	return toolSendKeys(args)
}

func toolGetWindowHandle(args map[string]interface{}) (interface{}, error) {
	handle, err := wd.GetWindowHandle()
	if err != nil {
		return errorResult(fmt.Errorf("get window handle failed: %w", err)), nil
	}
	return textResult(handle), nil
}

func toolGetWindowHandles(args map[string]interface{}) (interface{}, error) {
	handles, err := wd.GetWindowHandles()
	if err != nil {
		return errorResult(fmt.Errorf("get window handles failed: %w", err)), nil
	}
	return textResult(prettyJSON(handles)), nil
}

func toolSwitchWindow(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	if handle == "" {
		handle = getString(args, "name")
	}
	if err := wd.SwitchWindow(handle); err != nil {
		return errorResult(fmt.Errorf("switch window failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Switched window: %s", handle)), nil
}

func toolSetWindowSize(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	width := getInt(args, "width")
	height := getInt(args, "height")
	if err := wd.SetWindowSize(handle, width, height); err != nil {
		return errorResult(fmt.Errorf("set window size failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Window size set: width=%d height=%d", width, height)), nil
}

func toolGetWindowSize(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	size, err := wd.GetWindowSize(handle)
	if err != nil {
		return errorResult(fmt.Errorf("get window size failed: %w", err)), nil
	}
	return textResult(prettyJSON(size)), nil
}

func toolSetWindowPosition(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	x := getInt(args, "x")
	y := getInt(args, "y")
	if err := wd.SetWindowPosition(handle, x, y); err != nil {
		return errorResult(fmt.Errorf("set window position failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Window position set: x=%d y=%d", x, y)), nil
}

func toolGetWindowPosition(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	position, err := wd.GetWindowPosition(handle)
	if err != nil {
		return errorResult(fmt.Errorf("get window position failed: %w", err)), nil
	}
	return textResult(prettyJSON(position)), nil
}

func toolMaximizeWindow(args map[string]interface{}) (interface{}, error) {
	handle := getString(args, "window_handle")
	if err := wd.MaximizeWindow(handle); err != nil {
		return errorResult(fmt.Errorf("maximize window failed: %w", err)), nil
	}
	return textResult("Window maximized."), nil
}

func toolCloseWindow(args map[string]interface{}) (interface{}, error) {
	if err := wd.CloseWindow(); err != nil {
		return errorResult(fmt.Errorf("close window failed: %w", err)), nil
	}
	return textResult("Window closed."), nil
}

func toolTouchClick(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchClick(x, y); err != nil {
		return errorResult(fmt.Errorf("touch click failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch clicked: (%d, %d)", x, y)), nil
}

func toolTouchDoubleClick(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchDoubleClick(x, y); err != nil {
		return errorResult(fmt.Errorf("touch double click failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch double clicked: (%d, %d)", x, y)), nil
}

func toolTouchLongClick(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchLongClick(x, y); err != nil {
		return errorResult(fmt.Errorf("touch long click failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch long clicked: (%d, %d)", x, y)), nil
}

func toolTouchDown(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchDown(x, y); err != nil {
		return errorResult(fmt.Errorf("touch down failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch down: (%d, %d)", x, y)), nil
}

func toolTouchUp(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchUp(x, y); err != nil {
		return errorResult(fmt.Errorf("touch up failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch up: (%d, %d)", x, y)), nil
}

func toolTouchMove(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	if err := wd.TouchMove(x, y); err != nil {
		return errorResult(fmt.Errorf("touch move failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch move: (%d, %d)", x, y)), nil
}

func toolTouchScroll(args map[string]interface{}) (interface{}, error) {
	x, y := getInt(args, "x"), getInt(args, "y")
	xoffset, yoffset := getInt(args, "xoffset"), getInt(args, "yoffset")
	if err := wd.TouchScroll(x, y, xoffset, yoffset); err != nil {
		return errorResult(fmt.Errorf("touch scroll failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch scroll: (%d, %d) offset=(%d, %d)", x, y, xoffset, yoffset)), nil
}

func toolTouchFlick(args map[string]interface{}) (interface{}, error) {
	xspeed, yspeed := getInt(args, "xspeed"), getInt(args, "yspeed")
	if err := wd.TouchFlick(xspeed, yspeed); err != nil {
		return errorResult(fmt.Errorf("touch flick failed: %w", err)), nil
	}
	return textResult(fmt.Sprintf("Touch flick: xspeed=%d yspeed=%d", xspeed, yspeed)), nil
}

func toolWebDriverRequest(args map[string]interface{}) (interface{}, error) {
	method := strings.ToUpper(requireString(args, "method"))
	path := requireString(args, "path")
	sessionID := getString(args, "session_id")
	payload := getObject(args, "payload")

	value, raw, err := wd.RawRequest(sessionID, method, path, payload)
	if err != nil {
		return errorResult(fmt.Errorf("webdriver request failed: %w", err)), nil
	}
	if len(value) > 0 {
		return textResult(prettyRawJSON(value)), nil
	}
	return textResult(prettyRawJSON(raw)), nil
}

// ==================== Helpers ====================

func getString(args map[string]interface{}, key string) string {
	if v, ok := args[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

func requireString(args map[string]interface{}, key string) string {
	return strings.TrimSpace(getString(args, key))
}

func getStringWithDefault(args map[string]interface{}, key, def string) string {
	if v := getString(args, key); v != "" {
		return v
	}
	return def
}

func getInt(args map[string]interface{}, key string) int {
	if v, ok := args[key]; ok {
		switch n := v.(type) {
		case float64:
			return int(n)
		case float32:
			return int(n)
		case int:
			return n
		case int64:
			return int(n)
		case json.Number:
			var i int
			fmt.Sscanf(string(n), "%d", &i)
			return i
		}
	}
	return 0
}

func getObject(args map[string]interface{}, key string) interface{} {
	if v, ok := args[key]; ok {
		return v
	}
	return nil
}

func hasKey(args map[string]interface{}, key string) bool {
	_, ok := args[key]
	return ok
}

func resolveElementID(args map[string]interface{}) (string, error) {
	if elementID := getString(args, "element_id"); elementID != "" {
		return elementID, nil
	}
	selector := getString(args, "selector")
	if selector == "" {
		return "", fmt.Errorf("element_id or selector is required")
	}
	using := getStringWithDefault(args, "using", "accessibility id")
	return wd.FindElement(using, selector)
}

func parseJSONString(raw json.RawMessage) (string, error) {
	if len(raw) == 0 {
		return "", nil
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return s, nil
	}
	return strings.TrimSpace(string(raw)), nil
}

func parseJSONBool(raw json.RawMessage) (bool, error) {
	var value bool
	if err := json.Unmarshal(raw, &value); err != nil {
		return false, err
	}
	return value, nil
}

func parseJSONObject(raw json.RawMessage) (map[string]interface{}, error) {
	var value map[string]interface{}
	if err := json.Unmarshal(raw, &value); err != nil {
		return nil, err
	}
	return value, nil
}

func mapInt(value map[string]interface{}, key string) (int, bool) {
	raw, ok := value[key]
	if !ok {
		return 0, false
	}
	switch v := raw.(type) {
	case int:
		return v, true
	case int32:
		return int(v), true
	case int64:
		return int(v), true
	case float32:
		return int(v), true
	case float64:
		return int(v), true
	default:
		return 0, false
	}
}

func extractElementID(raw json.RawMessage) string {
	var value map[string]interface{}
	if err := json.Unmarshal(raw, &value); err != nil {
		return ""
	}
	if elementID, ok := value["ELEMENT"].(string); ok {
		return elementID
	}
	if elementID, ok := value[w3cElementKey].(string); ok {
		return elementID
	}
	return ""
}

func extractElementIDs(raw json.RawMessage) []string {
	var items []map[string]interface{}
	if err := json.Unmarshal(raw, &items); err != nil {
		return nil
	}
	elementIDs := make([]string, 0, len(items))
	for _, item := range items {
		if elementID, ok := item["ELEMENT"].(string); ok && elementID != "" {
			elementIDs = append(elementIDs, elementID)
			continue
		}
		if elementID, ok := item[w3cElementKey].(string); ok && elementID != "" {
			elementIDs = append(elementIDs, elementID)
		}
	}
	return elementIDs
}

func parseMouseButton(button string) int {
	switch strings.ToLower(strings.TrimSpace(button)) {
	case "middle":
		return 1
	case "right":
		return 2
	default:
		return 0
	}
}

func previewString(s string, limit int) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return ""
	}
	s = strings.ReplaceAll(s, "\r", " ")
	s = strings.ReplaceAll(s, "\n", " ")
	s = strings.ReplaceAll(s, "\t", " ")
	if len(s) <= limit {
		return s
	}
	return s[:limit] + "...(truncated)"
}

func summarizeForLog(v interface{}) string {
	if v == nil {
		return "null"
	}
	switch x := v.(type) {
	case ToolResult:
		return summarizeToolResult(x)
	case *ToolResult:
		if x == nil {
			return "null"
		}
		return summarizeToolResult(*x)
	case string:
		return previewString(x, 300)
	case json.RawMessage:
		return previewString(prettyRawJSON(x), 300)
	}

	data, err := json.Marshal(v)
	if err != nil {
		return previewString(fmt.Sprintf("%v", v), 300)
	}
	return previewString(string(data), 300)
}

func summarizeToolResult(tr ToolResult) string {
	parts := make([]string, 0, len(tr.Content))
	for _, block := range tr.Content {
		switch block.Type {
		case "text":
			parts = append(parts, "text="+previewString(block.Text, 180))
		case "image":
			parts = append(parts, fmt.Sprintf("image(mime=%s,size=%d)", block.MimeType, len(block.Data)))
		default:
			parts = append(parts, block.Type)
		}
	}
	return fmt.Sprintf("ToolResult{isError=%t, content=[%s]}", tr.IsError, strings.Join(parts, ", "))
}

func stringToKeyValues(s string) []string {
	values := make([]string, 0, len([]rune(s)))
	for _, r := range s {
		values = append(values, string(r))
	}
	return values
}

func prettyJSON(v interface{}) string {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return fmt.Sprintf("%v", v)
	}
	return string(data)
}

func prettyRawJSON(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var value interface{}
	if err := json.Unmarshal(raw, &value); err == nil {
		return prettyJSON(value)
	}
	return strings.TrimSpace(string(raw))
}

func textResult(text string) ToolResult {
	return ToolResult{
		Content: []ContentBlock{{Type: "text", Text: text}},
	}
}

func errorResult(err error) ToolResult {
	return ToolResult{
		Content: []ContentBlock{{Type: "text", Text: fmt.Sprintf("ERROR: %v", err)}},
		IsError: true,
	}
}

func permissiveSchema() map[string]interface{} {
	return map[string]interface{}{
		"type":                 "object",
		"properties":           map[string]interface{}{},
		"additionalProperties": true,
	}
}

// ==================== Main ====================

func main() {
	loadConfig()

	wd = newWDClient()

	s := NewMCPServer("WinAppDriver", "1.1.0", "MCP Server for Windows App Driver")

	s.AddTool("winapp_create_session", "Create a WinAppDriver session and launch an app", toolCreateSession)
	s.AddTool("winapp_delete_session", "Close the current WinAppDriver session", toolDeleteSession)
	s.AddTool("winapp_get_sessions", "List all active WinAppDriver sessions", toolGetSessions)
	s.AddTool("winapp_get_status", "Get WinAppDriver service status", toolGetStatus)
	s.AddTool("winapp_set_timeout", "Set WinAppDriver session timeout", toolSetTimeout)
	s.AddTool("winapp_launch_app", "Launch the app attached to the current session", toolAppLaunch)
	s.AddTool("winapp_close_app", "Close the app attached to the current session", toolAppClose)
	s.AddTool("winapp_navigate_back", "Navigate back in the current session", toolNavigateBack)
	s.AddTool("winapp_navigate_forward", "Navigate forward in the current session", toolNavigateForward)
	s.AddTool("winapp_get_title", "Get current window title", toolGetTitle)
	s.AddTool("winapp_get_location", "Get current session location info", toolGetLocation)
	s.AddTool("winapp_get_orientation", "Get current session orientation", toolGetOrientation)

	s.AddTool("winapp_find_element", "Find a single element", toolFindElement)
	s.AddTool("winapp_find_elements", "Find multiple elements", toolFindElements)
	s.AddTool("winapp_find_element_from_element", "Find a child element from a parent element", toolFindElementFromElement)
	s.AddTool("winapp_find_elements_from_element", "Find child elements from a parent element", toolFindElementsFromElement)
	s.AddTool("winapp_get_active_element", "Get the active element", toolGetActiveElement)
	s.AddTool("winapp_click_element", "Click an element by element id or selector", toolClickElement)
	s.AddTool("winapp_clear_element", "Clear text from an element", toolClearElement)
	s.AddTool("winapp_send_keys_to_element", "Send text to an element by element id or selector", toolSendKeysToElement)
	s.AddTool("winapp_get_element_text", "Get element text", toolGetElementText)
	s.AddTool("winapp_get_element_attribute", "Get element attribute", toolGetElementAttribute)
	s.AddTool("winapp_get_element_name", "Get element name", toolGetElementName)
	s.AddTool("winapp_is_element_displayed", "Check whether an element is displayed", toolIsElementDisplayed)
	s.AddTool("winapp_is_element_enabled", "Check whether an element is enabled", toolIsElementEnabled)
	s.AddTool("winapp_is_element_selected", "Check whether an element is selected", toolIsElementSelected)
	s.AddTool("winapp_get_element_location", "Get element location", toolGetElementLocation)
	s.AddTool("winapp_get_element_location_in_view", "Get element location in view", toolGetElementLocationInView)
	s.AddTool("winapp_get_element_size", "Get element size", toolGetElementSize)
	s.AddTool("winapp_get_element_screenshot", "Take a screenshot of an element", toolGetElementScreenshot)
	s.AddTool("winapp_compare_elements", "Compare whether two element references are equal", toolCompareElements)

	s.AddTool("winapp_mouse_move", "Move mouse to coordinates or element", toolMouseMove)
	s.AddTool("winapp_mouse_click", "Click mouse at current or specified coordinates", toolMouseClick)
	s.AddTool("winapp_mouse_double_click", "Double click mouse at current or specified coordinates", toolMouseDoubleClick)
	s.AddTool("winapp_mouse_button_down", "Press a mouse button", toolMouseButtonDown)
	s.AddTool("winapp_mouse_button_up", "Release a mouse button", toolMouseButtonUp)
	s.AddTool("winapp_send_keys", "Send keys to the active element or a target element", toolSendKeys)
	s.AddTool("winapp_press_keys", "Alias of winapp_send_keys for keyboard shortcuts", toolPressKeys)

	s.AddTool("winapp_get_window_handle", "Get current window handle", toolGetWindowHandle)
	s.AddTool("winapp_get_window_handles", "Get all window handles", toolGetWindowHandles)
	s.AddTool("winapp_switch_window", "Switch to a window handle", toolSwitchWindow)
	s.AddTool("winapp_set_window_size", "Set window size", toolSetWindowSize)
	s.AddTool("winapp_get_window_size", "Get window size", toolGetWindowSize)
	s.AddTool("winapp_set_window_position", "Set window position", toolSetWindowPosition)
	s.AddTool("winapp_get_window_position", "Get window position", toolGetWindowPosition)
	s.AddTool("winapp_maximize_window", "Maximize current or specified window", toolMaximizeWindow)
	s.AddTool("winapp_close_window", "Close current window", toolCloseWindow)

	s.AddTool("winapp_get_screenshot", "Take a screenshot of the current window", toolGetScreenshot)
	s.AddTool("winapp_get_page_source", "Get XML source of the current window", toolGetPageSource)
	s.AddTool("winapp_touch_click", "Perform a touch click", toolTouchClick)
	s.AddTool("winapp_touch_double_click", "Perform a touch double click", toolTouchDoubleClick)
	s.AddTool("winapp_touch_long_click", "Perform a touch long click", toolTouchLongClick)
	s.AddTool("winapp_touch_down", "Perform a touch down action", toolTouchDown)
	s.AddTool("winapp_touch_up", "Perform a touch up action", toolTouchUp)
	s.AddTool("winapp_touch_move", "Perform a touch move action", toolTouchMove)
	s.AddTool("winapp_touch_scroll", "Perform a touch scroll action", toolTouchScroll)
	s.AddTool("winapp_touch_flick", "Perform a touch flick action", toolTouchFlick)

	s.AddTool("winapp_webdriver_request", "Call any WinAppDriver endpoint directly using method, path and payload", toolWebDriverRequest)

	// Backward-compatible aliases.
	s.AddTool("winapp_screenshot", "Alias of winapp_get_screenshot", toolGetScreenshot)
	s.AddTool("winapp_get_source", "Alias of winapp_get_page_source", toolGetPageSource)
	s.AddTool("winapp_click", "Alias of winapp_mouse_click", toolMouseClick)

	addr := fmt.Sprintf("%s:%d", cfg.MCPHost, cfg.MCPPort)

	log.Printf("========================================")
	log.Printf("  WinAppDriver MCP Server (Go)")
	log.Printf("========================================")
	log.Printf("  MCP Address:  http://%s/sse", addr)
	log.Printf("  WinAppDriver: %s", cfg.WinAppDriverURL)
	log.Printf("  HTTP Timeout: %ds", cfg.WinAppDriverTimeout)
	log.Printf("  MCP Verbose:  %t", cfg.MCPLogVerbose)
	log.Printf("  Auto-start:   %t", cfg.AutoStart)
	log.Printf("========================================")

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	server := &http.Server{
		Addr:    addr,
		Handler: s,
	}

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[FATAL] Server error: %v", err)
		}
	}()

	log.Printf("[INFO] MCP Server listening on http://%s", addr)
	<-quit

	log.Printf("[INFO] Shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = server.Shutdown(ctx)
	wd.stopWinAppDriver()
	log.Printf("[INFO] Server stopped.")
}
