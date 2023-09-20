package keeper

import (
	"fmt"

	sdk "github.com/cosmos/cosmos-sdk/types"
	sdkerrors "github.com/cosmos/cosmos-sdk/types/errors"

	"github.com/Canto-Network/Canto/v7/x/coinswap/types"
)

func (k Keeper) swapCoins(ctx sdk.Context, sender, recipient sdk.AccAddress, coinSold, coinBought sdk.Coin) error {
	lptDenom, err := k.GetLptDenomFromDenoms(ctx, coinSold.Denom, coinBought.Denom)
	if err != nil {
		return err
	}

	poolAddr := types.GetReservePoolAddr(lptDenom)
	if err := k.bk.SendCoins(ctx, sender, poolAddr, sdk.NewCoins(coinSold)); err != nil {
		return err
	}

	if recipient.Empty() {
		recipient = sender
	}

	return k.bk.SendCoins(ctx, poolAddr, recipient, sdk.NewCoins(coinBought))
}

/*
*
Calculate the amount of another token to be received based on the exact amount of tokens sold
@param exactSoldCoin : sold coin
@param soldTokenDenom : received token's denom
@return : amount of the token that will be received
*/
func (k Keeper) calculateWithExactInput(ctx sdk.Context, exactSoldCoin sdk.Coin, boughtTokenDenom string) (sdk.Int, error) {
	lptDenom, err := k.GetLptDenomFromDenoms(ctx, exactSoldCoin.Denom, boughtTokenDenom)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	reservePoolAddress := types.GetReservePoolAddr(lptDenom).String()
	reservePool, err := k.GetPoolBalances(ctx, reservePoolAddress)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	inputReserve := reservePool.AmountOf(exactSoldCoin.Denom)
	outputReserve := reservePool.AmountOf(boughtTokenDenom)

	if !inputReserve.IsPositive() {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrInsufficientFunds, fmt.Sprintf("reserve pool insufficient funds, actual [%s%s]", inputReserve.String(), exactSoldCoin.Denom))
	}
	if !outputReserve.IsPositive() {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrInsufficientFunds, fmt.Sprintf("reserve pool insufficient funds, actual [%s%s]", outputReserve.String(), boughtTokenDenom))
	}
	param := k.GetParams(ctx)

	boughtTokenAmt := GetInputPrice(exactSoldCoin.Amount, inputReserve, outputReserve, param.Fee)
	return boughtTokenAmt, nil
}

/*
*
Sell exact amount of a token for buying another, one of them must be standard token
@param input: exact amount of the token to be sold
@param output: min amount of the token to be bought
@param sender: address of the sender
@param receipt: address of the receiver
@return: actual amount of the token to be bought
*/
func (k Keeper) TradeExactInputForOutput(ctx sdk.Context, input types.Input, output types.Output) (sdk.Int, error) {
	boughtTokenAmt, err := k.calculateWithExactInput(ctx, input.Coin, output.Coin.Denom)
	if err != nil {
		return sdk.ZeroInt(), err
	}
	// assert that the calculated amount is more than the
	// minimum amount the buyer is willing to buy.
	if boughtTokenAmt.LT(output.Coin.Amount) {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrConstraintNotMet, fmt.Sprintf("insufficient amount of %s, user expected: %s, actual: %s", output.Coin.Denom, output.Coin.Amount.String(), boughtTokenAmt.String()))
	}
	boughtToken := sdk.NewCoin(output.Coin.Denom, boughtTokenAmt)

	inputAddress, err := sdk.AccAddressFromBech32(input.Address)
	if err != nil {
		return sdk.ZeroInt(), err
	}
	outputAddress, err := sdk.AccAddressFromBech32(output.Address)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	standardDenom := k.GetStandardDenom(ctx)
	var quoteCoinToSwap sdk.Coin

	if boughtToken.Denom != standardDenom {
		quoteCoinToSwap = boughtToken
	} else {
		quoteCoinToSwap = input.Coin
	}

	maxSwapAmount, err := k.GetMaximumSwapAmount(ctx, quoteCoinToSwap.Denom)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	if quoteCoinToSwap.Amount.GT(maxSwapAmount.Amount) {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrConstraintNotMet, fmt.Sprintf("expected swap amount %s%s exceeding swap amount limit %s%s", quoteCoinToSwap.Amount.String(), quoteCoinToSwap.Denom, maxSwapAmount.Amount.String(), maxSwapAmount.Denom))
	}

	if err := k.swapCoins(ctx, inputAddress, outputAddress, input.Coin, boughtToken); err != nil {
		return sdk.ZeroInt(), err
	}
	return boughtTokenAmt, nil
}

/*
*
Calculate the amount of the token to be paid based on the exact amount of the token to be bought
@param exactBoughtCoin
@param soldTokenDenom
@return: actual amount of the token to be paid
*/
func (k Keeper) calculateWithExactOutput(ctx sdk.Context, exactBoughtCoin sdk.Coin, soldTokenDenom string) (sdk.Int, error) {
	lptDenom, err := k.GetLptDenomFromDenoms(ctx, exactBoughtCoin.Denom, soldTokenDenom)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	poolAddr := types.GetReservePoolAddr(lptDenom).String()
	reservePool, err := k.GetPoolBalances(ctx, poolAddr)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	outputReserve := reservePool.AmountOf(exactBoughtCoin.Denom)
	inputReserve := reservePool.AmountOf(soldTokenDenom)

	if !inputReserve.IsPositive() {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrInsufficientFunds, fmt.Sprintf("reserve pool insufficient balance: [%s%s]", inputReserve.String(), soldTokenDenom))
	}
	if !outputReserve.IsPositive() {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrInsufficientFunds, fmt.Sprintf("reserve pool insufficient balance: [%s%s]", outputReserve.String(), exactBoughtCoin.Denom))
	}
	if exactBoughtCoin.Amount.GTE(outputReserve) {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrInsufficientFunds, fmt.Sprintf("reserve pool insufficient balance of %s, user expected: %s, actual: %s", exactBoughtCoin.Denom, exactBoughtCoin.Amount.String(), outputReserve.String()))
	}
	param := k.GetParams(ctx)

	soldTokenAmt := GetOutputPrice(exactBoughtCoin.Amount, inputReserve, outputReserve, param.Fee)
	return soldTokenAmt, nil
}

/*
*
Buy exact amount of a token by specifying the max amount of another token, one of them must be standard token
@param input : max amount of the token to be paid
@param output : exact amount of the token to be bought
@param sender : address of the sender
@param receipt : address of the receiver
@return : actual amount of the token to be paid
*/
func (k Keeper) TradeInputForExactOutput(ctx sdk.Context, input types.Input, output types.Output) (sdk.Int, error) {
	soldTokenAmt, err := k.calculateWithExactOutput(ctx, output.Coin, input.Coin.Denom)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	// assert that the calculated amount is less than the
	// max amount the buyer is willing to pay.
	if soldTokenAmt.GT(input.Coin.Amount) {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrConstraintNotMet, fmt.Sprintf("insufficient amount of %s, user expected: %s, actual: %s", input.Coin.Denom, input.Coin.Amount.String(), soldTokenAmt.String()))
	}
	soldToken := sdk.NewCoin(input.Coin.Denom, soldTokenAmt)

	inputAddress, err := sdk.AccAddressFromBech32(input.Address)
	if err != nil {
		return sdk.ZeroInt(), err
	}
	outputAddress, err := sdk.AccAddressFromBech32(output.Address)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	standardDenom := k.GetStandardDenom(ctx)
	var quoteCoinToSwap sdk.Coin

	if soldToken.Denom != standardDenom {
		quoteCoinToSwap = soldToken
	} else {
		quoteCoinToSwap = output.Coin
	}

	maxSwapAmount, err := k.GetMaximumSwapAmount(ctx, quoteCoinToSwap.Denom)
	if err != nil {
		return sdk.ZeroInt(), err
	}

	if quoteCoinToSwap.Amount.GT(maxSwapAmount.Amount) {
		return sdk.ZeroInt(), sdkerrors.Wrap(types.ErrConstraintNotMet, fmt.Sprintf("expected swap amount %s%s exceeding swap amount limit %s%s", quoteCoinToSwap.Amount.String(), quoteCoinToSwap.Denom, maxSwapAmount.Amount.String(), maxSwapAmount.Denom))
	}

	if err := k.swapCoins(ctx, inputAddress, outputAddress, soldToken, output.Coin); err != nil {
		return sdk.ZeroInt(), err
	}

	return soldTokenAmt, nil
}

func (k Keeper) GetMaximumSwapAmount(ctx sdk.Context, denom string) (sdk.Coin, error) {
	params := k.GetParams(ctx)
	for _, coin := range params.MaxSwapAmount {
		if coin.Denom == denom {
			return coin, nil
		}
	}
	return sdk.Coin{}, sdkerrors.Wrap(types.ErrInvalidDenom, fmt.Sprintf("invalid denom: %s, denom is not whitelisted", denom))
}

// GetInputPrice returns the amount of coins bought (calculated) given the input amount being sold (exact)
// The fee is included in the input coins being bought
// https://github.com/runtimeverification/verified-smart-contracts/blob/uniswap/uniswap/x-y-k.pdf
func GetInputPrice(inputAmt, inputReserve, outputReserve sdk.Int, fee sdk.Dec) sdk.Int {
	deltaFee := sdk.OneDec().Sub(fee)
	inputAmtWithFee := inputAmt.Mul(sdk.NewIntFromBigInt(deltaFee.BigInt()))
	numerator := inputAmtWithFee.Mul(outputReserve)
	denominator := inputReserve.Mul(sdk.NewIntWithDecimal(1, sdk.Precision)).Add(inputAmtWithFee)
	return numerator.Quo(denominator)
}

// GetOutputPrice returns the amount of coins sold (calculated) given the output amount being bought (exact)
// The fee is included in the output coins being bought
func GetOutputPrice(outputAmt, inputReserve, outputReserve sdk.Int, fee sdk.Dec) sdk.Int {
	deltaFee := sdk.OneDec().Sub(fee)
	numerator := inputReserve.Mul(outputAmt).Mul(sdk.NewIntWithDecimal(1, sdk.Precision))
	denominator := (outputReserve.Sub(outputAmt)).Mul(sdk.NewIntFromBigInt(deltaFee.BigInt()))
	return numerator.Quo(denominator).Add(sdk.OneInt())
}
