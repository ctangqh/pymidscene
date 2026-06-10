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

// ==================== Config ====================

type Config struct {
	MCPHost              string
	MCPPort             int
	WinAppDriverHost    string
	WinAppDriverPort    int
	WinAppDriverURL     string
	WinAppDriverTimeout int
	AutoStart           bool
}

var cfg Config

func loadConfig() {
	envPaths := []string{".env", "dist/.env", "./dist/.env"}
	for _, p := range envPaths {
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
			log.Printf("[INFO] Loaded .env from: %s", p)
			break
		}
	}

	cfg.MCPHost = getEnv("MCP_HOST", "0.0.0.0")
	cfg.MCPPort = getEnvInt("MCP_PORT", 55001)
	cfg.WinAppDriverHost = getEnv("WINAPPDRIVER_HOST", "127.0.0.1")
	cfg.WinAppDriverPort = getEnvInt("WINAPPDRIVER_PORT", 4723)
	cfg.WinAppDriverTimeout = getEnvInt("WINAPPDRIVER_HTTP_TIMEOUT", 120)
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

// ==================== WinAppDriver Client ====================

type WDClient struct {
	baseURL string
	timeout time.Duration
	session string
	mu      sync.RWMutex
	client  *http.Client
}

var wd *WDClient

func newWDClient() *WDClient {
	return &WDClient{
		baseURL: cfg.WinAppDriverURL,
		timeout: time.Duration(cfg.WinAppDriverTimeout) * time.Second,
		client: &http.Client{Timeout: time.Duration(cfg.WinAppDriverTimeout) * time.Second},
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

func (c *WDClient) do(method, path string, body interface{}) ([]byte, int, error) {
	var bodyStr string
	if body != nil {
		data, _ := json.Marshal(body)
		bodyStr = string(data)
	}

	req, err := http.NewRequest(method, c.baseURL+path, strings.NewReader(bodyStr))
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	if c.getSession() != "" {
		req.Header.Set("X-Session-Id", c.getSession())
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)
	return bodyBytes, resp.StatusCode, nil
}

func (c *WDClient) CreateSession(app, appArgs, platformName, deviceName string) (string, error) {
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
		return "", fmt.Errorf("create session HTTP %d: %s", code, string(body))
	}

	var resp struct {
		SessionID string `json:"sessionId"`
	}
	json.Unmarshal(body, &resp)
	if resp.SessionID == "" {
		// Some WinAppDriver versions return differently
		var resp2 map[string]interface{}
		json.Unmarshal(body, &resp2)
		if v, ok := resp2["sessionId"].(string); ok {
			resp.SessionID = v
		}
	}

	c.setSession(resp.SessionID)
	return resp.SessionID, nil
}

func (c *WDClient) DeleteSession() error {
	sess := c.getSession()
	if sess == "" {
		return nil
	}
	_, code, _ := c.do("DELETE", "/session/"+sess, nil)
	c.setSession("")
	if code != 200 && code != 204 {
		return fmt.Errorf("delete session HTTP %d", code)
	}
	return nil
}

func (c *WDClient) GetSessions() ([]string, error) {
	body, code, err := c.do("GET", "/sessions", nil)
	if err != nil {
		return nil, err
	}
	if code != 200 {
		return nil, fmt.Errorf("HTTP %d: %s", code, string(body))
	}
	var sessions []string
	json.Unmarshal(body, &sessions)
	return sessions, nil
}

func (c *WDClient) GetStatus() (string, error) {
	body, _, err := c.do("GET", "/status", nil)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

func (c *WDClient) Screenshot() ([]byte, error) {
	sess := c.getSession()
	if sess == "" {
		return nil, fmt.Errorf("no active session")
	}
	body, code, err := c.do("GET", "/session/"+sess+"/screenshot", nil)
	if err != nil {
		return nil, fmt.Errorf("screenshot failed: %w", err)
	}
	if code != 200 {
		return nil, fmt.Errorf("screenshot HTTP %d: %s", code, string(body))
	}

	var result struct {
		Value string `json:"value"`
	}
	json.Unmarshal(body, &result)
	return base64.StdEncoding.DecodeString(result.Value)
}

func (c *WDClient) GetSource() (string, error) {
	sess := c.getSession()
	if sess == "" {
		return "", fmt.Errorf("no active session")
	}
	body, code, err := c.do("GET", "/session/"+sess+"/source", nil)
	if err != nil {
		return "", err
	}
	if code != 200 {
		return "", fmt.Errorf("get source HTTP %d: %s", code, string(body))
	}
	return string(body), nil
}

func (c *WDClient) FindElement(strategy, selector string) (string, error) {
	sess := c.getSession()
	if sess == "" {
		return "", fmt.Errorf("no active session")
	}

	body, code, err := c.do("POST", "/session/"+sess+"/element", map[string]string{
		"using": strategy,
		"value": selector,
	})
	if err != nil {
		return "", err
	}
	if code != 200 && code != 201 {
		return "", fmt.Errorf("find element HTTP %d: %s", code, string(body))
	}

	var resp struct {
		Value struct{ ELEMENT string `json:"ELEMENT"` } `json:"value"`
	}
	json.Unmarshal(body, &resp)
	return resp.Value.ELEMENT, nil
}

func (c *WDClient) ClickElement(elementID string) error {
	sess := c.getSession()
	if sess == "" {
		return fmt.Errorf("no active session")
	}
	_, code, err := c.do("POST", fmt.Sprintf("/session/%s/element/%s/click", sess, elementID), nil)
	if err != nil {
		return err
	}
	if code != 200 && code != 204 {
		return fmt.Errorf("click element HTTP %d", code)
	}
	return nil
}

func (c *WDClient) ClickAt(x, y int) error {
	sess := c.getSession()
	if sess == "" {
		return fmt.Errorf("no active session")
	}
	if _, code, err := c.do("POST", fmt.Sprintf("/session/%s/moveto", sess), map[string]int{
		"xoffset": x,
		"yoffset": y,
	}); err != nil {
		return err
	} else if code != 200 && code != 204 {
		return fmt.Errorf("move to HTTP %d", code)
	}

	_, code, err := c.do("POST", fmt.Sprintf("/session/%s/click", sess), map[string]int{
		"button": 0,
	})
	if err != nil {
		return err
	}
	if code != 200 && code != 204 {
		return fmt.Errorf("click at HTTP %d", code)
	}
	return nil
}

func (c *WDClient) SendKeysToElement(elementID, text string) error {
	if err := c.ClickElement(elementID); err != nil {
		return fmt.Errorf("focus element failed: %w", err)
	}
	return pasteText(text)
}

func (c *WDClient) SendKeys(keys string) error {
	sess := c.getSession()
	if sess == "" {
		return fmt.Errorf("no active session")
	}
	return pasteText(keys)
}

func pasteText(text string) error {
	cmd := exec.Command(
		"powershell",
		"-NoProfile",
		"-Command",
		"Set-Clipboard -Value $env:PYMID_TEXT; Add-Type -AssemblyName System.Windows.Forms; Start-Sleep -Milliseconds 100; [System.Windows.Forms.SendKeys]::SendWait('^v')",
	)
	cmd.Env = append(os.Environ(), "PYMID_TEXT="+text)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("paste text failed: %v (%s)", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func (c *WDClient) PressKeys(keys string) error {
	sess := c.getSession()
	if sess == "" {
		return fmt.Errorf("no active session")
	}
	return sendWinAppKeys(keys)
}

func sendWinAppKeys(keys string) error {
	keySequence := normalizeSendKeys(keys)
	if keySequence == "" {
		return fmt.Errorf("empty key sequence")
	}
	cmd := exec.Command(
		"powershell",
		"-NoProfile",
		"-Command",
		"Add-Type -AssemblyName System.Windows.Forms; Start-Sleep -Milliseconds 100; [System.Windows.Forms.SendKeys]::SendWait($env:PYMID_KEYS)",
	)
	cmd.Env = append(os.Environ(), "PYMID_KEYS="+keySequence)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("send keys failed: %v (%s)", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func normalizeSendKeys(keys string) string {
	keys = strings.TrimSpace(keys)
	if keys == "" {
		return ""
	}

	upper := strings.ToUpper(keys)
	switch upper {
	case "ALT+F4":
		return "%{F4}"
	case "CTRL+S":
		return "^s"
	case "CTRL+SHIFT+S":
		return "^+s"
	case "ESC", "ESCAPE":
		return "{ESC}"
	case "ENTER":
		return "{ENTER}"
	case "TAB":
		return "{TAB}"
	}

	if strings.ContainsAny(keys, "^%+{}") {
		return keys
	}
	return keys
}

func (c *WDClient) ClearElement(elementID string) error {
	sess := c.getSession()
	if sess == "" {
		return fmt.Errorf("no active session")
	}
	_, code, err := c.do("POST", fmt.Sprintf("/session/%s/element/%s/clear", sess, elementID), nil)
	if err != nil {
		return err
	}
	if code != 200 && code != 204 {
		return fmt.Errorf("clear element HTTP %d", code)
	}
	return nil
}

// ==================== MCP Protocol Types ====================

type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      interface{}      `json:"id,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
	ID      interface{}     `json:"id,omitempty"`
}

type JSONRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type MCPInitializeResult struct {
	ProtocolVersion string                    `json:"protocolVersion"`
	Capabilities    map[string]interface{}   `json:"capabilities"`
	ServerInfo      map[string]interface{}   `json:"serverInfo"`
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
	Type string `json:"type"`
	Text string `json:"text,omitempty"`
	// For image content
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
	sessions   map[string]chan string // sessionID -> SSE event channel
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
	s.tools[name] = ToolDefinition{
		Name:        name,
		Description: description,
		InputSchema: map[string]interface{}{
			"type":                 "object",
			"properties":           map[string]interface{}{},
			"additionalProperties": true,
		},
		Handler: handler,
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
		"version":     "1.0.0",
		"description": "MCP Server for Windows App Driver",
		"tools":       s.tools,
	})
}

func (s *MCPServer) handleSSE(w http.ResponseWriter, r *http.Request) {
	// Set SSE headers
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

	// Send endpoint event
	fmt.Fprintf(w, "event: endpoint\ndata: /messages?session_id=%s\n\n", sessionID)
	flusher.Flush()

	// Heartbeat ticker
	heartbeat := time.NewTicker(15 * time.Second)
	defer func() {
		heartbeat.Stop()
		s.sessionsMu.Lock()
		delete(s.sessions, sessionID)
		s.sessionsMu.Unlock()
		close(eventChan)
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
		http.Error(w, "Parse error", http.StatusBadRequest)
		return
	}

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
				"version": "1.0.0",
			},
		}
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
		s.sendSessionResponse(sessionID, req.ID, map[string]interface{}{"tools": toolsList})

	case "tools/call":
		var params ToolCallParams
		if req.Params != nil {
			json.Unmarshal(req.Params, &params)
		}

		tool, ok := s.tools[params.Name]
		if !ok {
			s.sendSessionError(sessionID, req.ID, -32602, fmt.Sprintf("Unknown tool: %s", params.Name))
			return
		}

		result, err := tool.Handler(params.Arguments)
		if err != nil {
			s.sendSessionResponse(sessionID, req.ID, ToolResult{
				Content: []ContentBlock{ContentBlock{Type: "text", Text: err.Error()}},
				IsError: true,
			})
			return
		}

		// Wrap result as ToolResult
		if tr, ok := result.(ToolResult); ok {
			s.sendSessionResponse(sessionID, req.ID, tr)
		} else {
			s.sendSessionResponse(sessionID, req.ID, result)
		}

	default:
		// Notifications do not require an SSE response.
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
	s.enqueueSessionMessage(sessionID, resp)
}

func (s *MCPServer) sendSessionError(sessionID string, id interface{}, code int, message string) {
	resp := JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &JSONRPCError{Code: code, Message: message},
	}
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
	app := getString(args, "app")
	platformName := getStringWithDefault(args, "platform_name", "Windows")
	deviceName := getStringWithDefault(args, "device_name", "WindowsPC")

	sessID, err := wd.CreateSession(app, "", platformName, deviceName)
	if err != nil {
		return ToolResult{
			Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: create session failed: %v", err)}},
			IsError: true,
		}, nil
	}
	return ToolResult{
		Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Session created: %s | App: %s", sessID, app)}},
	}, nil
}

func toolDeleteSession(args map[string]interface{}) (interface{}, error) {
	if err := wd.DeleteSession(); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: delete session failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: "Session closed."}}}, nil
}

func toolGetSessions(args map[string]interface{}) (interface{}, error) {
	sessions, err := wd.GetSessions()
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: get sessions failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Active sessions: %d\n%s", len(sessions), strings.Join(sessions, "\n"))}}}, nil
}

func toolGetStatus(args map[string]interface{}) (interface{}, error) {
	status, err := wd.GetStatus()
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: get status failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: status}}, IsError: false}, nil
}

func toolScreenshot(args map[string]interface{}) (interface{}, error) {
	img, err := wd.Screenshot()
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: screenshot failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{
		{Type: "image", Data: base64.StdEncoding.EncodeToString(img), MimeType: "image/png"},
	}}, nil
}

func toolGetSource(args map[string]interface{}) (interface{}, error) {
	src, err := wd.GetSource()
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: get source failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: src}}, IsError: false}, nil
}

func toolClickElement(args map[string]interface{}) (interface{}, error) {
	selector := getString(args, "selector")
	using := getStringWithDefault(args, "using", "accessibility id")

	eid, err := wd.FindElement(using, selector)
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: find element %s failed: %v", selector, err)}}, IsError: true}, nil
	}
	if err := wd.ClickElement(eid); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: click element %s failed: %v", selector, err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Clicked: %s", selector)}}, IsError: false}, nil
}

func toolClick(args map[string]interface{}) (interface{}, error) {
	x := getInt(args, "x")
	y := getInt(args, "y")
	if err := wd.ClickAt(x, y); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: click at (%d,%d) failed: %v", x, y, err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Clicked at (%d, %d)", x, y)}}, IsError: false}, nil
}

func toolSendKeys(args map[string]interface{}) (interface{}, error) {
	keys := getString(args, "keys")
	selector := getString(args, "selector")
	using := getStringWithDefault(args, "using", "accessibility id")

	if selector != "" {
		eid, err := wd.FindElement(using, selector)
		if err != nil {
			return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: find element %s failed: %v", selector, err)}}, IsError: true}, nil
		}
		if err := wd.SendKeysToElement(eid, keys); err != nil {
			return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: send keys to %s failed: %v", selector, err)}}, IsError: true}, nil
		}
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Sent to %s: %s", selector, keys)}}, IsError: false}, nil
	}

	if err := wd.SendKeys(keys); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: send keys failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Sent global keys: %s", keys)}}, IsError: false}, nil
}

func toolPressKeys(args map[string]interface{}) (interface{}, error) {
	keys := getString(args, "keys")
	if err := wd.PressKeys(keys); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: press keys failed: %v", err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Pressed keys: %s", keys)}}, IsError: false}, nil
}

func toolClearElement(args map[string]interface{}) (interface{}, error) {
	selector := getString(args, "selector")
	using := getStringWithDefault(args, "using", "accessibility id")

	eid, err := wd.FindElement(using, selector)
	if err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: find element %s failed: %v", selector, err)}}, IsError: true}, nil
	}
	if err := wd.ClearElement(eid); err != nil {
		return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("ERROR: clear element %s failed: %v", selector, err)}}, IsError: true}, nil
	}
	return ToolResult{Content: []ContentBlock{ContentBlock{Type: "text", Text: fmt.Sprintf("Cleared: %s", selector)}}, IsError: false}, nil
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

func getStringWithDefault(args map[string]interface{}, key, def string) string {
	if v, ok := args[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return def
}

func getInt(args map[string]interface{}, key string) int {
	if v, ok := args[key]; ok {
		switch n := v.(type) {
		case float64:
			return int(n)
		case int:
			return n
		}
	}
	return 0
}

func stringToKeyValues(s string) []string {
	values := make([]string, 0, len([]rune(s)))
	for _, r := range s {
		values = append(values, string(r))
	}
	return values
}

// ==================== Main ====================

func main() {
	loadConfig()

	wd = newWDClient()

	s := NewMCPServer("WinAppDriver", "1.0.0", "MCP Server for Windows App Driver")

	// Register all tools
	s.AddTool("winapp_create_session", "Create a WinAppDriver session and launch an app", toolCreateSession)
	s.AddTool("winapp_delete_session", "Close the current WinAppDriver session", toolDeleteSession)
	s.AddTool("winapp_get_sessions", "List all active WinAppDriver sessions", toolGetSessions)
	s.AddTool("winapp_get_status", "Get WinAppDriver service status", toolGetStatus)
	s.AddTool("winapp_screenshot", "Take a screenshot of the current window", toolScreenshot)
	s.AddTool("winapp_get_source", "Get XML source of the current window", toolGetSource)
	s.AddTool("winapp_click_element", "Click an element by selector", toolClickElement)
	s.AddTool("winapp_click", "Click at screen coordinates", toolClick)
	s.AddTool("winapp_send_keys", "Send text to an element or active window", toolSendKeys)
	s.AddTool("winapp_press_keys", "Send keyboard shortcut keys to the active window", toolPressKeys)
	s.AddTool("winapp_clear_element", "Clear text from an element", toolClearElement)

	addr := fmt.Sprintf("%s:%d", cfg.MCPHost, cfg.MCPPort)

	log.Printf("========================================")
	log.Printf("  WinAppDriver MCP Server (Go)")
	log.Printf("========================================")
	log.Printf("  MCP Address:  http://%s/sse", addr)
	log.Printf("  WinAppDriver: %s", cfg.WinAppDriverURL)
	log.Printf("  HTTP Timeout: %ds", cfg.WinAppDriverTimeout)
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
	server.Shutdown(ctx)
	log.Printf("[INFO] Server stopped.")
}
