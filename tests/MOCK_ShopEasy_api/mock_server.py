import asyncio
import logging
import grpc
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Header

# Import the generated gRPC files
import shopeasy_pb2
import shopeasy_pb2_grpc

app = FastAPI(title="ShopEasy Mock HTTP API")

# ==========================================
# 1. HTTP MOCK (FastAPI)
# ==========================================
def verify_token(authorization: str = Header(None)):
    """Simulates API Key validation matching {{env.SHOPEASY_API_KEY}}"""
    if authorization != "Bearer mock_secret_token_123":
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")

@app.get("/v1/orders/{order_id}", dependencies=[Depends(verify_token)])
async def get_order(order_id: str):
    """Simulates fetching an order from the database"""
    # Simple logic to make the response feel dynamic
    status = "Shipped" if "1" in order_id else "Processing"
    return {
        "order_id": order_id,
        "status": status,
        "estimated_delivery": "2026-07-08",
        "items_count": 2
    }

# ==========================================
# 2. gRPC MOCK (grpcio)
# ==========================================
class PaymentGatewayServicer(shopeasy_pb2_grpc.PaymentGatewayServicer):
    async def ProcessRefund(self, request, context):
        """Simulates processing a refund over a secure internal microservice"""
        
        # Check for the injected header: "x-admin-key: {{env.ADMIN_RPC_KEY}}"
        metadata = dict(context.invocation_metadata())
        if metadata.get("x-admin-key") != "mock_grpc_admin_key":
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or missing x-admin-key metadata")
        
        logging.info(f"[gRPC] Processing refund for order {request.order_id} (Amount: ${request.amount})")
        
        return shopeasy_pb2.RefundResponse(
            success=True,
            transaction_id=f"TXN-REFUND-{request.order_id}-889"
        )

async def serve_grpc():
    server = grpc.aio.server()
    shopeasy_pb2_grpc.add_PaymentGatewayServicer_to_server(PaymentGatewayServicer(), server)
    server.add_insecure_port('[::]:50051')
    logging.info("gRPC Server running on port 50051")
    await server.start()
    await server.wait_for_termination()

async def serve_http():
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="info")
    server = uvicorn.Server(config)
    logging.info("FastAPI HTTP Server running on port 8001")
    await server.serve()

async def main():
    logging.basicConfig(level=logging.INFO)
    await asyncio.gather(serve_http(), serve_grpc())

if __name__ == "__main__":
    asyncio.run(main())