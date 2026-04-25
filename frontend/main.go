package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App struct
type App struct {
	ctx        context.Context
	pythonCmd  *exec.Cmd
	apiPort    int
	pythonPath string
}

// NewApp creates a new App application struct
func NewApp() *App {
	return &App{}
}

// startup is called when the app starts. The context is saved
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
}

// domReady is called after front-end resources have been loaded
func (a *App) domReady(ctx context.Context) {
	// 启动 Python API 服务
	go a.startPythonService()
}

// beforeClose is called when the application is about to quit
func (a *App) beforeClose(ctx context.Context) (prevent bool) {
	a.stopPythonService()
	return false
}

// shutdown is called at application termination
func (a *App) shutdown(ctx context.Context) {
	a.stopPythonService()
}

// findFreePort 查找可用端口
func findFreePort() int {
	listener, err := net.Listen("tcp", ":0")
	if err != nil {
		return 0
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()
	return port
}

// findPython 查找 Python 解释器路径
func findPython() string {
	candidates := []string{"python3", "python"}
	
	if runtime.GOOS == "windows" {
		candidates = append(candidates, 
			`C:\Python310\python.exe`,
			`C:\Python311\python.exe`,
			`C:\Python312\python.exe`,
		)
	}
	
	for _, cmd := range candidates {
		if _, err := exec.LookPath(cmd); err == nil {
			return cmd
		}
	}
	
	return "python3"
}

// findVMCModule 查找 vmc 模块路径
func (a *App) findVMCModule() string {
	exePath, err := os.Executable()
	if err == nil {
		exeDir := filepath.Dir(exePath)
		possiblePaths := []string{
			filepath.Join(exeDir, "python", "site-packages"),
			filepath.Join(exeDir, "..", "lib", "python3", "site-packages"),
		}
		for _, p := range possiblePaths {
			if _, err := os.Stat(p); err == nil {
				return p
			}
		}
	}
	
	// 开发环境
	wd, _ := os.Getwd()
	devPath := filepath.Join(wd, "src")
	if _, err := os.Stat(devPath); err == nil {
		return devPath
	}
	
	return ""
}

// startPythonService 启动 Python API 服务
func (a *App) startPythonService() {
	a.pythonPath = findPython()
	a.apiPort = findFreePort()
	
	if a.apiPort == 0 {
		log.Println("Cannot find free port for API server")
		return
	}
	
	log.Printf("Starting Python API server on port %d...", a.apiPort)
	
	pythonPath := os.Getenv("PYTHONPATH")
	vmcModulePath := a.findVMCModule()
	
	args := []string{
		"-m", "uvicorn",
		"vivado_ai.api.server:app",
		"--host", "127.0.0.1",
		"--port", fmt.Sprintf("%d", a.apiPort),
		"--log-level", "warning",
	}
	
	cmd := exec.Command(a.pythonPath, args...)
	
	env := os.Environ()
	if vmcModulePath != "" {
		if pythonPath != "" {
			env = append(env, fmt.Sprintf("PYTHONPATH=%s:%s", vmcModulePath, pythonPath))
		} else {
			env = append(env, fmt.Sprintf("PYTHONPATH=%s", vmcModulePath))
		}
	}
	cmd.Env = env
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	
	if err := cmd.Start(); err != nil {
		log.Printf("Failed to start Python API server: %v", err)
		return
	}
	
	a.pythonCmd = cmd
	log.Printf("Python API server started on port %d", a.apiPort)
	
	// 等待服务就绪
	time.Sleep(2 * time.Second)
	
	// 通知前端 API 地址
	apiURL := fmt.Sprintf("http://127.0.0.1:%d", a.apiPort)
	runtime.EventsEmit(a.ctx, "apiReady", apiURL)
}

// stopPythonService 停止 Python API 服务
func (a *App) stopPythonService() {
	if a.pythonCmd != nil && a.pythonCmd.Process != nil {
		log.Println("Stopping Python API server...")
		a.pythonCmd.Process.Kill()
		a.pythonCmd.Wait()
		a.pythonCmd = nil
	}
}

// GetAPIPort 返回 API 端口（供前端使用）
func (a *App) GetAPIPort() int {
	return a.apiPort
}

// GetAPIURL 返回完整的 API URL
func (a *App) GetAPIURL() string {
	return fmt.Sprintf("http://127.0.0.1:%d", a.apiPort)
}

func main() {
	app := NewApp()
	
	err := wails.Run(&options.App{
		Title:     "VMC - Vivado Methodology Checker",
		Width:     900,
		Height:    700,
		MinWidth:  600,
		MinHeight: 500,
		AssetServer: &assetserver.Options{
			Assets: nil,
		},
		BackgroundColour: &options.RGBA{R: 15, G: 15, B: 26, A: 1},
		OnStartup:        app.startup,
		OnDomReady:       app.domReady,
		OnBeforeClose:    app.beforeClose,
		OnShutdown:       app.shutdown,
		Bind: []interface{}{
			app,
		},
	})
	
	if err != nil {
		log.Fatal(err)
	}
}
