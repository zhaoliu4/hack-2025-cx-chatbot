package main

import (
	"os"
	"path/filepath"
	"time"

	returnDataCastle "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/returns"
	"github.com/happyreturns/gohelpers/common"
	"github.com/happyreturns/gohelpers/grpc/client_connector"
	"github.com/happyreturns/gohelpers/log"
	"github.com/joho/godotenv"

	mcp_golang "github.com/metoro-io/mcp-golang"
	"github.com/metoro-io/mcp-golang/transport/http"
)

func main() {
	// Get the executable path
	exePath, err := os.Executable()
	if err != nil {
		println("Error getting executable path:", err.Error())
	}

	// Get the directory of the executable
	exeDir := filepath.Dir(exePath)

	// Move up one directory to the project root (from mcp-server to root)
	rootDir := filepath.Dir(exeDir)

	// Load .env from the root directory
	err = godotenv.Load(filepath.Join(rootDir, ".env"))
	if err != nil {
		// Try loading from current directory as fallback
		err = godotenv.Load()
		if err != nil {
			// Log error but continue as environment variables might be set elsewhere
			println("Error loading .env file:", err.Error())
		}
	}

	app := "mcp-server"

	logger := log.NewLogger(app, "local")
	dataCastleHost := "data-castle-dev.happyreturns.com:443"
	dataCastleConnection, err := client_connector.
		NewClientConn("returns-service", logger.Entry).
		UseTLS().
		SetTimeout(30 * time.Second).
		Dial(dataCastleHost)
	if err != nil {
		logger.WithError(err).Fatal("Failed to connect to Data Castle")
	}
	db := common.GormDBConnWithService(app)
	returnsDCClient := returnDataCastle.NewReturnServiceClient(dataCastleConnection)
	toolsManager := NewToolsManager(logger, db, returnsDCClient)

	done := make(chan struct{})

	// Basic HTTP Server
	transport := http.NewHTTPTransport("/mcp")
	transport.WithAddr(":53000")

	// Std IO
	// transport := stdio.NewStdioServerTransport()

	server := mcp_golang.NewServer(transport)
	err = server.RegisterTool(toolsManager.GetReturnByConfirmationCodeTool())
	if err != nil {
		logger.WithError(err).Fatal("Failed to register tool")
	}

	err = server.Serve()
	if err != nil {
		logger.WithError(err).Fatal("Failed to start mcp server")
	}

	<-done
}
