package main

import (
	"os"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	returnDataCastle "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/returns"
	"github.com/happyreturns/gohelpers/common"
	"github.com/happyreturns/gohelpers/grpc/client_connector"
	"github.com/happyreturns/gohelpers/log"
)

func main() {
	os.Setenv("DATABASE_CONNECTION_STRING", "postgres://username:password@db-dev.happyreturns.com/happyreturns")

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

	// Create a new MCP server
	s := server.NewMCPServer(
		"Demo",
		"1.0.0",
		server.WithToolCapabilities(false),
	)

	// Add tool
	tool := mcp.NewTool("get_return_by_confirmation_code",
		mcp.WithDescription(`Get return information by confirmation code, which is a 8-character string starting with 'HR'. 
			Basic return information is returned by default. The optional fields can be used to request additional information.`),
		mcp.WithString("confirmation_code",
			mcp.Required(),
			mcp.Description("The confirmation code to get the return"),
		),
		mcp.WithBoolean("with_item_details",
			mcp.Description("Request additional information about each item in the return"),
		),
		mcp.WithBoolean("with_dropoff_details",
			mcp.Description("Request additional information about the requested dropoff method and the actual dropoff method"),
		),
		mcp.WithBoolean("with_refund_details",
			mcp.Description("Request additional information about the refund for the return"),
		),
		mcp.WithBoolean("with_shipping_details",
			mcp.Description("Request additional information about where the return is currently at and the shipping information for the return, including the item to retailer warehouse shipping, return bar to hub shipping, and hub to retailer warehouse shipping"),
		),
	)

	// Add tool handler
	s.AddTool(tool, toolsManager.GetReturnByConfirmationCodeToolHandler)

	// // Start the stdio server
	if err := server.ServeStdio(s); err != nil {
		logger.Fatalf("Server error: %v\n", err)
	}

	// Start the SSE server
	// sseServer := server.NewSSEServer(s)
	// httpServer := &http.Server{
	// 	Addr:    ":53000",
	// 	Handler: sseServer,
	// }

	// if err := httpServer.ListenAndServe(); err != nil {
	// 	logger.Fatalf("Server error: %v\n", err)
	// }
}
