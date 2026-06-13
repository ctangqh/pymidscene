package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

type Config struct {
	MCPHost             string
	MCPPort             int
	MCPLogVerbose       bool
	HypiumPython        string
	HypiumConnector     string
	HypiumDeviceSN      string
	HypiumReportPath    string
	HypiumLogLevel      string
	HypiumConnectorHost string
	HypiumConnectorPort int
	HypiumTempDir       string
}

type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string         `json:"jsonrpc"`
	ID      interface{}    `json:"id,omitempty"`
	Result  interface{}    `json:"result,omitempty"`
	Error   *JSONRPCError  `json:"error,omitempty"`
}

type JSONRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type ToolCallParams struct {
	Name      string                 `json:"name"`
	Arguments map[string]interface{} `json:"arguments"`
}

type ContentBlock struct {
	Type     string `json:"type"`
	Text     string `json:"text,omitempty"`
	Data     string `json:"data,omitempty"`
	MimeType string `json:"mimeType,omitempty"`
}

type ToolResult struct {
	Content []ContentBlock `json:"content"`
	IsError bool           `json:"isError,omitempty"`
}

type ToolDefinition struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	InputSchema map[string]interface{} `json:"inputSchema"`
	Handler     ToolHandler            `json:"-"`
}

type HypiumHelperResponse struct {
	OK          bool   `json:"ok"`
	Text        string `json:"text,omitempty"`
	ImageBase64 string `json:"image_base64,omitempty"`
	MimeType    string `json:"mime_type,omitempty"`
	Error       string `json:"error,omitempty"`
}

type ToolHandler func(args map[string]interface{}) (ToolResult, error)

type MCPServer struct {
	tools      map[string]ToolDefinition
	sessions   map[string]chan string
	sessionsMu sync.RWMutex
}

var cfg Config

func loadConfig() {
	configPaths := []string{"mcp.conf", "dist/mcp.conf", "./dist/mcp.conf"}
	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		configPaths = append([]string{
			filepath.Join(exeDir, "mcp.conf"),
			filepath.Join(exeDir, "dist", "mcp.conf"),
		}, configPaths...)
	}
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
	cfg.MCPPort = getEnvInt("MCP_PORT", 55002)
	cfg.MCPLogVerbose = getEnvBool("MCP_LOG_VERBOSE", false)
	cfg.HypiumPython = getEnv("HYPIUM_PYTHON", "")
	cfg.HypiumConnector = getEnv("HYPIUM_CONNECTOR", "hdc")
	cfg.HypiumDeviceSN = getEnv("HYPIUM_DEVICE_SN", "")
	cfg.HypiumReportPath = getEnv("HYPIUM_REPORT_PATH", "")
	cfg.HypiumLogLevel = getEnv("HYPIUM_LOG_LEVEL", "info")
	cfg.HypiumConnectorHost = getEnv("HYPIUM_CONNECTOR_HOST", "")
	cfg.HypiumConnectorPort = getEnvInt("HYPIUM_CONNECTOR_PORT", 0)
	cfg.HypiumTempDir = getEnv("HYPIUM_TEMP_DIR", "")
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
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

func NewMCPServer() *MCPServer {
	return &MCPServer{
		tools:    make(map[string]ToolDefinition),
		sessions: make(map[string]chan string),
	}
}

func (s *MCPServer) AddTool(name, description string, inputSchema map[string]interface{}, handler ToolHandler) {
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
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"name":        "Hypium MCP Server",
		"version":     "0.1.0",
		"description": "MCP Server for Hypium/OpenHarmony",
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

	fmt.Fprintf(w, "event: endpoint\ndata: /messages?session_id=%s\n\n", sessionID)
	flusher.Flush()

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
		result := map[string]interface{}{
			"protocolVersion": "2024-11-05",
			"capabilities": map[string]interface{}{
				"tools": map[string]interface{}{
					"listChanged": false,
				},
			},
			"serverInfo": map[string]interface{}{
				"name":    "Hypium",
				"version": "0.1.0",
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
			_ = json.Unmarshal(req.Params, &params)
		}
		tool, ok := s.tools[params.Name]
		if !ok {
			s.sendSessionError(sessionID, req.ID, -32602, fmt.Sprintf("Unknown tool: %s", params.Name))
			return
		}
		result, err := tool.Handler(params.Arguments)
		if err != nil {
			s.sendSessionResponse(sessionID, req.ID, errorResult(err))
			return
		}
		s.sendSessionResponse(sessionID, req.ID, result)
	default:
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
	ch, ok := s.sessions[sessionID]
	s.sessionsMu.RUnlock()
	if !ok {
		return
	}
	select {
	case ch <- string(data):
	default:
		log.Printf("[WARN] session queue full, dropping message for session=%s", sessionID)
	}
}

func textResult(text string) ToolResult {
	return ToolResult{
		Content: []ContentBlock{{Type: "text", Text: text}},
	}
}

func imageResult(data, mimeType, text string) ToolResult {
	content := []ContentBlock{
		{Type: "image", Data: data, MimeType: mimeType},
	}
	if strings.TrimSpace(text) != "" {
		content = append(content, ContentBlock{Type: "text", Text: text})
	}
	return ToolResult{Content: content}
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

func helperPath() string {
	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		candidates := []string{
			filepath.Join(exeDir, "helper.py"),
			filepath.Join(exeDir, "dist", "helper.py"),
			filepath.Join(".", "helper.py"),
		}
		for _, candidate := range candidates {
			if _, err := os.Stat(candidate); err == nil {
				return candidate
			}
		}
	}
	return filepath.Join(".", "helper.py")
}

func resolvePython() string {
	if cfg.HypiumPython != "" {
		return cfg.HypiumPython
	}
	exeDir := "."
	if exe, err := os.Executable(); err == nil {
		exeDir = filepath.Dir(exe)
	}
	candidates := []string{
		filepath.Join(exeDir, "..", "..", ".venv", "Scripts", "python.exe"),
		filepath.Join(exeDir, "..", "..", ".venv", "Scripts", "python"),
		filepath.Join("..", "..", ".venv", "Scripts", "python.exe"),
		filepath.Join("..", "..", ".venv", "Scripts", "python"),
		"python",
		"python3",
	}
	for _, candidate := range candidates {
		if candidate == "python" || candidate == "python3" {
			if path, err := exec.LookPath(candidate); err == nil {
				return path
			}
			continue
		}
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	if runtime.GOOS == "windows" {
		return "python"
	}
	return "python3"
}

func helperEnv() []string {
	env := os.Environ()
	pairs := map[string]string{
		"HYPIUM_CONNECTOR":       cfg.HypiumConnector,
		"HYPIUM_DEVICE_SN":       cfg.HypiumDeviceSN,
		"HYPIUM_REPORT_PATH":     cfg.HypiumReportPath,
		"HYPIUM_LOG_LEVEL":       cfg.HypiumLogLevel,
		"HYPIUM_CONNECTOR_HOST":  cfg.HypiumConnectorHost,
		"HYPIUM_CONNECTOR_PORT":  strconv.Itoa(cfg.HypiumConnectorPort),
		"HYPIUM_TEMP_DIR":        cfg.HypiumTempDir,
		"HYPIUM_MCP_LOG_VERBOSE": strconv.FormatBool(cfg.MCPLogVerbose),
	}
	for key, value := range pairs {
		if strings.TrimSpace(value) == "" || value == "0" {
			continue
		}
		env = append(env, fmt.Sprintf("%s=%s", key, value))
	}
	return env
}

func runHelper(action string, args map[string]interface{}) (HypiumHelperResponse, error) {
	helperArgs, err := json.Marshal(args)
	if err != nil {
		return HypiumHelperResponse{}, err
	}

	python := resolvePython()
	cmd := exec.CommandContext(context.Background(), python, helperPath(), action, "--arguments", string(helperArgs))
	if helper := helperPath(); helper != "" {
		cmd.Dir = filepath.Dir(helper)
	}
	cmd.Env = helperEnv()

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	verboseLog("[HYPIUM] helper start action=%s args=%s", action, string(helperArgs))
	if err := cmd.Run(); err != nil {
		return HypiumHelperResponse{}, fmt.Errorf("helper failed: %w stderr=%s stdout=%s", err, strings.TrimSpace(stderr.String()), strings.TrimSpace(stdout.String()))
	}

	var resp HypiumHelperResponse
	if err := json.Unmarshal(stdout.Bytes(), &resp); err != nil {
		return HypiumHelperResponse{}, fmt.Errorf("invalid helper response: %w raw=%s", err, strings.TrimSpace(stdout.String()))
	}
	if !resp.OK {
		if resp.Error == "" {
			resp.Error = "helper returned failure"
		}
		return HypiumHelperResponse{}, fmt.Errorf(resp.Error)
	}
	return resp, nil
}

func makeHelperTool(action string) ToolHandler {
	return func(args map[string]interface{}) (ToolResult, error) {
		resp, err := runHelper(action, args)
		if err != nil {
			return ToolResult{}, err
		}
		if resp.ImageBase64 != "" {
			mimeType := resp.MimeType
			if mimeType == "" {
				mimeType = "image/jpeg"
			}
			return imageResult(resp.ImageBase64, mimeType, resp.Text), nil
		}
		return textResult(resp.Text), nil
	}
}

func registerTools(s *MCPServer) {
	s.AddTool("hypium_get_source", "Dump current Hypium UI tree as JSON text", permissiveSchema(), makeHelperTool("hypium_get_source"))
	s.AddTool("hypium_screenshot", "Capture current screen and return image data", permissiveSchema(), makeHelperTool("hypium_screenshot"))
	s.AddTool("hypium_click", "Click a Hypium selector or coordinates", permissiveSchema(), makeHelperTool("hypium_click"))
	s.AddTool("hypium_input", "Input text into a Hypium selector or coordinates", permissiveSchema(), makeHelperTool("hypium_input"))
	s.AddTool("hypium_clear_text", "Clear text for a Hypium selector", permissiveSchema(), makeHelperTool("hypium_clear_text"))
	s.AddTool("hypium_go_back", "Go back on current device", permissiveSchema(), makeHelperTool("hypium_go_back"))
	s.AddTool("hypium_go_home", "Go home on current device", permissiveSchema(), makeHelperTool("hypium_go_home"))
	s.AddTool("hypium_start_app", "Start app by package name", permissiveSchema(), makeHelperTool("hypium_start_app"))
	s.AddTool("hypium_stop_app", "Stop app by package name", permissiveSchema(), makeHelperTool("hypium_stop_app"))
	s.AddTool("hypium_current_app", "Get current foreground app info", permissiveSchema(), makeHelperTool("hypium_current_app"))
	s.AddTool("hypium_swipe", "Swipe current device", permissiveSchema(), makeHelperTool("hypium_swipe"))
	s.AddTool("hypium_find_component", "Resolve selector and return component metadata", permissiveSchema(), makeHelperTool("hypium_find_component"))
	s.AddTool("hypium_ai_click", "Reserved AI-level placeholder", permissiveSchema(), makeHelperTool("hypium_ai_click"))
	s.AddTool("hypium_ai_input", "Reserved AI-level placeholder", permissiveSchema(), makeHelperTool("hypium_ai_input"))
	s.AddTool("hypium_ai_extract", "Reserved AI-level placeholder", permissiveSchema(), makeHelperTool("hypium_ai_extract"))
	s.AddTool("hypium_ai_assert", "Reserved AI-level placeholder", permissiveSchema(), makeHelperTool("hypium_ai_assert"))
	s.AddTool("hypium_close", "Close current helper-side connection", permissiveSchema(), makeHelperTool("hypium_close"))
}

func main() {
	loadConfig()
	s := NewMCPServer()
	registerTools(s)

	addr := fmt.Sprintf("%s:%d", cfg.MCPHost, cfg.MCPPort)
	log.Printf("========================================")
	log.Printf("  Hypium MCP Server (Go)")
	log.Printf("========================================")
	log.Printf("  MCP Address:  http://%s/sse", addr)
	log.Printf("  Python:       %s", resolvePython())
	log.Printf("  Connector:    %s", cfg.HypiumConnector)
	log.Printf("  Device SN:    %s", cfg.HypiumDeviceSN)
	log.Printf("  MCP Verbose:  %t", cfg.MCPLogVerbose)
	log.Printf("========================================")

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	httpServer := &http.Server{
		Addr:    addr,
		Handler: s,
	}

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[FATAL] Server error: %v", err)
		}
	}()

	<-quit
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("[WARN] Shutdown error: %v", err)
	}
}
