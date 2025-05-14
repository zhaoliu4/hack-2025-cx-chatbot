package main

import (
	"os"
	"time"

	returnDataCastle "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/returns"
	"github.com/happyreturns/gohelpers/common"
	"github.com/happyreturns/gohelpers/grpc/client_connector"
	"github.com/happyreturns/gohelpers/log"

	mcp_golang "github.com/metoro-io/mcp-golang"
	"github.com/metoro-io/mcp-golang/transport/http"
)

func main() {
	os.Setenv("DATABASE_CONNECTION_STRING", "postgres://username:password@db-dev.happyreturns.com/happyreturns")

	app := "mcp-server"

	logger := log.NewLogger(app, "local")
	dataCastleHost := "data-castle-dev.happyreturns.com:443"
	dataCastleConnection, err := client_connector.
		NewClientConn("returns-service", logger.Entry).
		UseTLS().
		SetTimeout(60 * time.Second).
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
