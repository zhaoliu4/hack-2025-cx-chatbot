package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"encoding/json"

	"github.com/jinzhu/gorm"
	"github.com/mark3labs/mcp-go/mcp"
	"google.golang.org/protobuf/types/known/fieldmaskpb"

	dcModels "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/models"
	returnDataCastle "github.com/happyreturns/data-castle/modules/returns-service/v1/grpc/gen/protos/returns"
	"github.com/happyreturns/gohelpers/log"
)

var (
	DropoffMethodMapping = map[string]string{
		"return-bar":            "Return Bar",
		"mail":                  "Mail",
		"mail-shopper-provided": "Shopper Provided Label Mail",
		"retailer-store":        "Retailer Store",
		"mail-nolabel":          "No Print Mail",
		"mail-nobox-nolabel":    "No Pack No Print Mail at Return Bar",
	}
	ReceivedChannelMapping = map[string]string{
		"app":                   "Return Bar Dropoff",
		"store-app":             "Retailer Store Dropoff",
		"hosted":                "Mail",
		"mail-nolabel":          "No Print Mail",
		"mail-nobox-nolabel":    "No Pack No Print Mail at Return Bar",
		"mail-shopper-provided": "Shopper Provided Label Mail",
		"retailer-dashboard":    "Approved by Retailer Dashboard",
		"returnless":            "Returnless Refund",
	}
)

type ReturnBag struct {
	ID          int64   `json:"id"`
	ReturnID    string  `json:"return_id"`
	LocationID  *string `json:"location_id"`
	RetailerID  *string `json:"retailer_id"`
	Barcode     string  `json:"barcode"`
	LabelLayout string  `json:"label_layout"`
}

type Shipment struct {
	ID               string     `json:"id"`
	Carrier          string     `json:"carrier"`
	Tracking         string     `json:"tracking"`
	Departure        *time.Time `json:"departure"`
	Arrival          *time.Time `json:"arrival"`
	EstimatedArrival *time.Time `json:"estimated_arrival"`
}

type ReturnBagInstance struct {
	ID          int64  `json:"id"`
	ReturnBagID int64  `json:"return_bag_id"`
	InstanceID  string `json:"instance_id"`
}

type TrackedUnit struct {
	ID        string     `json:"id"`
	Carrier   string     `json:"carrier"`
	Tracking  string     `json:"tracking"`
	Departure *time.Time `json:"departure"`
	Arrival   *time.Time `json:"arrival"`
}

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

func (tm *toolsManager) GetReturnByConfirmationCodeToolHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	confirmationCode, ok := request.Params.Arguments["confirmation_code"].(string)
	if !ok {
		return nil, errors.New("confirmation_code must be a string")
	}
	withItemDetails, ok := request.Params.Arguments["with_item_details"].(bool)
	if !ok {
		tm.logger.Warn("with_item_details must be a boolean")
	}
	withDropoffDetails, ok := request.Params.Arguments["with_dropoff_details"].(bool)
	if !ok {
		tm.logger.Warn("with_dropoff_details must be a boolean")
	}
	withRefundDetails, ok := request.Params.Arguments["with_refund_details"].(bool)
	if !ok {
		tm.logger.Warn("with_refund_details must be a boolean")
	}
	withShippingDetails, ok := request.Params.Arguments["with_shipping_details"].(bool)
	if !ok {
		tm.logger.Warn("with_shipping_details must be a boolean")
	}
	paths := []string{"return.processing_fees", "return.dropoff_method"}
	if withItemDetails {
		paths = append(paths, "return.instances")
	}
	if withDropoffDetails {
		paths = append(paths, "return.instances", "return.location")
	}
	if withRefundDetails {
		paths = append(paths, "return.instances.instance_refund", "return.retailer.retailer_hosted")
	}
	if withShippingDetails {
		paths = append(paths, "return.location", "return.return_shipment")
	}

	retrn, err := tm.GetReturnByConfirmation(confirmationCode, paths)
	if err != nil {
		return nil, err
	}
	retrn = sanitizeReturn(retrn)

	var stringBuilder strings.Builder
	stringBuilder.WriteString(fmt.Sprintf(`The return status is currently set to %s. `, retrn.GetStatus()))
	stringBuilder.WriteString(fmt.Sprintf(`The expected total refund amount is %s if all items are returned and received. Partial return may result in partial refund. `, retrn.GetTotal()))
	if withItemDetails {
		stringBuilder.WriteString("Item details are included in the `instances` field of the return JSON object below. ")
		stringBuilder.WriteString("Whether an item is received/dropped-off or not is indicated by the `received_at` field in the `instances` list. ")
	}
	if withDropoffDetails {
		dropoffMethod := ""
		if retrn.GetDropoffMethod() != nil {
			dropoffMethod = DropoffMethodMapping[retrn.GetDropoffMethod().MethodId]
		}
		stringBuilder.WriteString(fmt.Sprintf("The dropoff method submitted by user was %s. The actual dropoff channel for each item is located at the `received_channel_id` field in the `instances` list. ", dropoffMethod))
		for _, instance := range retrn.GetInstances() {
			if instance.GetReceivedChannelId() != "" {
				instance.ReceivedChannelId = ReceivedChannelMapping[instance.GetReceivedChannelId()]
			}
		}
	}
	if withRefundDetails {
		stringBuilder.WriteString("The refund details for each item is located at the `refund` field in the `instances` list. Multiple items may share the same refund, as indicated by the same id in the `refund` field. ")
		stringBuilder.WriteString("The instance with empty `refund` field or `refunded_at` field is not refunded yet. ")
		stringBuilder.WriteString("If an item has valid `received_at` field but is not yet refunded, this is likely due to the refund settings in `retailer.retailer_hosted` field. ")
		stringBuilder.WriteString("`retailer.retailer_hosted.issue_refund_at` field controls the refund timing for all Mail returns. ")
		stringBuilder.WriteString("`retailer.retailer_hosted.nbnl_issue_refund_at` field controls the refund timing for all Mail returns except No Pack No Print. ")
		stringBuilder.WriteString("`retailer.retailer_hosted.issue_refund_at` field controls the refund timing for No Pack No Print Mail at Return Bar returns. ")
		stringBuilder.WriteString("`retailer.retailer_hosted.rb_issue_refund_at` field controls the refund timing for Return Bar dropoff returns. ")
	}
	if withShippingDetails {
		dropoffMethod := ""
		if retrn.GetDropoffMethod() != nil {
			dropoffMethod = retrn.GetDropoffMethod().MethodId
		}
		if dropoffMethod == "return-bar" {
			var returnBagBarcodes []string
			var returnBagIDs []int64
			var returnBagInstances []*ReturnBagInstance
			var hubInductedInstanceIDs []string

			returnBags, _ := tm.GetReturnBagsByReturnID(retrn.GetId())
			if len(returnBags) > 0 {
				stringBuilder.WriteString(fmt.Sprintf("The return has been dropped off at Return bar, there are %d return bags associated with the return. ", len(returnBags)))
				for _, returnBag := range returnBags {
					returnBagBarcodes = append(returnBagBarcodes, returnBag.Barcode)
					returnBagIDs = append(returnBagIDs, returnBag.ID)
				}
			} else {
				stringBuilder.WriteString("The return has not been dropped off at Return bar yet. ")
			}
			shipments, _ := tm.GetShipmentByReturnBagBarcodes(returnBagBarcodes)
			if len(shipments) > 0 {
				stringBuilder.WriteString(fmt.Sprintf("%d shipments have been created to ship the return bags to the hub. ", len(shipments)))
				for i, shipment := range shipments {
					stringBuilder.WriteString(fmt.Sprintf("The tracking number for shipment %d is %s. ", i+1, shipment.Tracking))
					if shipment.Departure != nil {
						stringBuilder.WriteString(fmt.Sprintf("The departure date is %s. ", shipment.Departure.Format(time.RFC3339)))
					}
					if shipment.EstimatedArrival != nil {
						stringBuilder.WriteString(fmt.Sprintf("The estimated arrival date is %s. ", shipment.EstimatedArrival.Format(time.RFC3339)))
					}
					if shipment.Arrival != nil {
						stringBuilder.WriteString(fmt.Sprintf("The delivery date is %s. ", shipment.Arrival.Format(time.RFC3339)))
					}
				}
			} else {
				stringBuilder.WriteString("No shipments have been created to ship the return bags to the hub yet. ")
			}
			if len(returnBagIDs) > 0 {
				returnBagInstances, _ = tm.FindHubInductedBags(returnBagIDs)
				hubInductedBagIDs := make(map[int64]struct{})
				for _, returnBagInstance := range returnBagInstances {
					hubInductedBagIDs[returnBagInstance.ReturnBagID] = struct{}{}
					hubInductedInstanceIDs = append(hubInductedInstanceIDs, returnBagInstance.InstanceID)
				}
				stringBuilder.WriteString(fmt.Sprintf("Out of the %d return bags in the return, %d have been inducted at the hub. ", len(returnBagIDs), len(hubInductedBagIDs)))
			}
			outboundShipments, _ := tm.GetOutboundShipmentsByInstanceIDs(hubInductedInstanceIDs)
			if len(outboundShipments) > 0 {
				stringBuilder.WriteString(fmt.Sprintf("The return bags have been processed by the hub and are being shipped to the retailer warehouse. There are %d outbound shipments created for the return bags. ", len(outboundShipments)))
				for i, outboundShipment := range outboundShipments {
					stringBuilder.WriteString(fmt.Sprintf("The tracking number for shipment %d is %s. ", i+1, outboundShipment.Tracking))
					if outboundShipment.Departure != nil {
						stringBuilder.WriteString(fmt.Sprintf("The departure date is %s. ", outboundShipment.Departure.Format(time.RFC3339)))
					}
					if outboundShipment.Arrival != nil {
						stringBuilder.WriteString(fmt.Sprintf("The delivery date is %s. ", outboundShipment.Arrival.Format(time.RFC3339)))
					}
				}
			} else {
				stringBuilder.WriteString("No outbound shipments have been created to ship the return bags to the retailer warehouse yet. ")
			}
		} else if retrn.ReturnShipment != nil {
			stringBuilder.WriteString("This is a mail return that will be shipped directly to the retailer warehouse. The Happy Returns hub will not be involved in the shipping process. ")
			stringBuilder.WriteString("The tracking number for the shipment is located at the `return_shipment.tracking` field. ")
			stringBuilder.WriteString("The shipment departure date is located at `return_shipment.departure` field, the estimated arrival date is located at `return_shipment.estimated_arrival` field, and the delivery date is located at `return_shipment.arrival` field. ")
		} else {
			stringBuilder.WriteString("Unable to determine the shipping status for this return. ")
		}
	}

	returnJsonObject, err := json.Marshal(retrn)
	if err != nil {
		return nil, err
	}
	stringBuilder.WriteString(fmt.Sprintf(`The JSON object of the return is provided below. It can be used as reference to answer return related questions, but it should not be displayed to the user directly. 
	JSON object: %s`, string(returnJsonObject)))

	content := stringBuilder.String()
	return mcp.NewToolResultText(content), nil
}

func (tm *toolsManager) RunReturnAnalyticalQueryToolHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	query, ok := request.Params.Arguments["query"].(string)
	if !ok {
		return nil, errors.New("query must be a string")
	}

	rows, err := tm.db.Debug().Raw(query).Rows()
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}

	var results []map[string]interface{}

	for rows.Next() {
		values := make([]interface{}, len(columns))
		valuePtrs := make([]interface{}, len(columns))
		for i := range values {
			valuePtrs[i] = &values[i]
		}

		if err := rows.Scan(valuePtrs...); err != nil {
			return nil, err
		}

		rowMap := make(map[string]interface{})
		for i, col := range columns {
			val := values[i]
			if b, ok := val.([]byte); ok {
				rowMap[col] = string(b)
			} else {
				rowMap[col] = val
			}
		}

		results = append(results, rowMap)
	}

	tm.logger.Info("Analytical query result: ", results)

	jsonResult, err := json.Marshal(results)
	if err != nil {
		tm.logger.WithError(err).Error("Failed to marshal query result to JSON")
		return nil, err
	}
	content := fmt.Sprintf("The result of the query is: %s", string(jsonResult))
	return mcp.NewToolResultText(content), nil
}

func (tm *toolsManager) GetReturnByConfirmation(confirmationCode string, paths []string) (*dcModels.Return, error) {
	resp, err := tm.returnsDCClient.GetReturnByConfirmationCode(context.Background(),
		&returnDataCastle.ReturnConfirmationCodeRequest{
			ConfirmationCode: confirmationCode,
			AdditionalFields: &fieldmaskpb.FieldMask{
				Paths: paths,
			},
		},
	)
	if resp.GetReturn() == nil || err != nil {
		tm.logger.WithError(err).Error("Failed to get return by confirmation code")
		return nil, err
	}

	return resp.GetReturn(), nil
}

func (tm *toolsManager) GetReturnBagsByReturnID(returnID string) ([]*ReturnBag, error) {
	var returnBags []*ReturnBag
	query := `select * from frontman.return_bag where return_id = ?`
	err := tm.db.Raw(query, returnID).Scan(&returnBags).Error
	if err != nil {
		tm.logger.WithError(err).Error("Failed to get return bags by return ID")
		return nil, err
	}
	return returnBags, nil
}

func (tm *toolsManager) GetShipmentByReturnBagBarcodes(barcodes []string) ([]*Shipment, error) {
	if len(barcodes) == 0 {
		return nil, errors.New("no return bag barcodes provided")
	}

	var shipments []*Shipment
	query := `select s.* from frontman.shipment s inner join frontman.location_shipment_return_bag lsrb on lsrb.shipment_id = s.id
	where lsrb.return_bag_barcode in (?)`
	err := tm.db.Raw(query, barcodes).Scan(&shipments).Error
	if err != nil {
		tm.logger.WithError(err).Error("Failed to get shipments by return bag barcodes")
		return nil, err
	}
	return shipments, nil
}

func (tm *toolsManager) FindHubInductedBags(returnBagIDs []int64) ([]*ReturnBagInstance, error) {
	if len(returnBagIDs) == 0 {
		return nil, errors.New("no return bag IDs provided")
	}

	var returnBagInstances []*ReturnBagInstance
	query := `select * from hub.return_bag_instance where return_bag_id in (?)`
	err := tm.db.Raw(query, returnBagIDs).Scan(&returnBagInstances).Error
	if err != nil {
		tm.logger.WithError(err).Error("Failed to get return bag instances by return bag IDs")
		return nil, err
	}
	return returnBagInstances, nil
}

func (tm *toolsManager) GetOutboundShipmentsByInstanceIDs(instanceIDs []string) ([]*TrackedUnit, error) {
	if len(instanceIDs) == 0 {
		return nil, errors.New("no instance IDs provided")
	}

	var trackedUnits []*TrackedUnit
	query := `select distinct tu.* from hub.tracked_unit tu inner join hub.outbound_shipment_item osi on osi.outbound_shipment_id = tu.outbound_shipment_id
	where osi.instance_id in (?)`
	err := tm.db.Raw(query, instanceIDs).Scan(&trackedUnits).Error
	if err != nil {
		tm.logger.WithError(err).Error("Failed to get outbound shipments by instance IDs")
		return nil, err
	}
	return trackedUnits, nil
}

func sanitizeReturn(retrn *dcModels.Return) *dcModels.Return {
	retrn.Itemization = ""
	retrn.CustomerIdentity.RecaptchaValue = ""
	retrn.CustomerIdentity.Token = ""
	for _, instance := range retrn.GetInstances() {
		instance.Purchase.Details = ""
	}
	return retrn
}
