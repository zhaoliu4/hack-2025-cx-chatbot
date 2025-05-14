package main

import (
	"context"
	"fmt"

	"github.com/jinzhu/gorm"
	mcp_golang "github.com/metoro-io/mcp-golang"
	"google.golang.org/protobuf/types/known/fieldmaskpb"

	dcModels "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/models"
	returnDataCastle "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/returns"
	"github.com/happyreturns/gohelpers/log"
)

type toolsManager struct {
	logger          *log.Logger
	db              *gorm.DB
	returnsDCClient returnDataCastle.ReturnServiceClient
}

func NewToolsManager(logger *log.Logger, db *gorm.DB, returnsDCClient returnDataCastle.ReturnServiceClient) *toolsManager {
	return &toolsManager{
		logger:          logger,
		db:              db,
		returnsDCClient: returnsDCClient,
	}
}

type GetReturnByConfirmationCodeToolArguments struct {
	ConfirmationCode string `json:"confirmation_code" jsonschema:"required,description=The confirmation code to get the return"`
}

func (tm *toolsManager) GetReturnByConfirmationCodeTool() (name string, description string, function interface{}) {
	name = "get_return_by_confirmation_code"
	description = "Get return information by confirmation code"
	function = func(arguments GetReturnByConfirmationCodeToolArguments) (*mcp_golang.ToolResponse, error) {
		confirmationCode := arguments.ConfirmationCode
		retrn, err := tm.GetReturnByConfirmation(confirmationCode)
		if err != nil {
			return nil, err
		}
		getReturnTemplate := "Return %s has status of %s and dropoff method of %s"
		content := fmt.Sprintf(
			getReturnTemplate,
			retrn.GetConfirmationCode(),
			retrn.GetStatus(),
			retrn.GetDropoffMethod().GetMethodId(),
		)
		return &mcp_golang.ToolResponse{
			Content: []*mcp_golang.Content{
				{
					Type: mcp_golang.ContentTypeText,
					TextContent: &mcp_golang.TextContent{
						Text: content,
					},
				},
			},
		}, nil
	}
	return
}

func (tm *toolsManager) GetReturnByConfirmation(confirmationCode string) (*dcModels.Return, error) {
	resp, err := tm.returnsDCClient.GetReturnByConfirmationCode(context.Background(),
		&returnDataCastle.ReturnConfirmationCodeRequest{
			ConfirmationCode: confirmationCode,
			AdditionalFields: &fieldmaskpb.FieldMask{
				Paths: []string{"return.dropoff_method"},
			},
		},
	)
	if resp.GetReturn() == nil || err != nil {
		tm.logger.WithError(err).Error("Failed to get return by confirmation code")
		return nil, err
	}

	return resp.GetReturn(), nil
}
