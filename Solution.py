from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func

app = Flask(__name__)

# --- PART 1: PRODUCT CREATION ENDPOINT ---

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json
    
    try:
        # Create new product (safely handling optional fields using .get)[cite: 2]
        product = Product(
            name=data.get('name'),
            sku=data.get('sku'),
            price=data.get('price', 0.0), # Decimal context[cite: 2]
            warehouse_id=data.get('warehouse_id')
        )
        
        db.session.add(product)
        # Flush gets the product.id without committing yet[cite: 2]
        db.session.flush()
        
        # Update inventory count
        inventory = Inventory(
            product_id=product.id,
            warehouse_id=data.get('warehouse_id'),
            quantity=data.get('initial_quantity', 0) # Handle optional quantity[cite: 2]
        )
        
        db.session.add(inventory)
        # Single atomic commit ensures data integrity[cite: 2]
        db.session.commit()
        
        return {"message": "Product created", "product_id": product.id}, 201
        
    except Exception as e:
        # Rollback handles duplicate SKUs or missing data safely[cite: 2]
        db.session.rollback()
        return {"error": "Failed to create product. Check for duplicate SKU or missing data."}, 400


# --- PART 3: LOW STOCK ALERTS ENDPOINT ---

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    try:
        # Define timeframe for "recent sales activity" (30 days)[cite: 2]
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # 1. Fetch inventory items below their threshold for the specific company[cite: 2]
        # Assumptions: threshold is stored on a per-product-type basis[cite: 2]
        low_stock_items = db.session.query(Inventory).join(Warehouse).filter(
            Warehouse.company_id == company_id,
            Inventory.current_quantity <= Inventory.low_stock_threshold
        ).all()

        alerts = []
        
        for item in low_stock_items:
            # 2. Check for recent sales activity in the ledger[cite: 2]
            recent_sales = db.session.query(InventoryLedger).filter(
                InventoryLedger.product_id == item.product_id,
                InventoryLedger.warehouse_id == item.warehouse_id,
                InventoryLedger.quantity_change < 0, # Deductions/Sales only
                InventoryLedger.timestamp >= thirty_days_ago
            ).first()

            if not recent_sales:
                continue # Only alert for products with recent activity[cite: 2]
            
            # 3. Calculate days until stockout based on historical velocity
            daily_sales = calculate_daily_sales(item.product_id, item.warehouse_id)
            
            # Edge case check: Prevent division by zero if sales velocity is flat
            if daily_sales > 0:
                days_out = int(item.current_quantity / daily_sales)
            else:
                days_out = 999 # Safe default indicating no immediate stockout risk

            # Return response in exact format required by specification[cite: 2]
            alerts.append({
                "product_id": item.product.id,
                "product_name": item.product.name,
                "sku": item.product.sku,
                "warehouse_id": item.warehouse.id,
                "warehouse_name": item.warehouse.name,
                "current_stock": item.current_quantity,
                "threshold": item.low_stock_threshold,
                "days_until_stockout": days_out,
                "supplier": {
                    "id": item.product.supplier.id,
                    "name": item.product.supplier.name,
                    "contact_email": item.product.supplier.contact_email
                }
            })

        return jsonify({
            "alerts": alerts,
            "total_alerts": len(alerts)
        }), 200

    except Exception as e:
        # Graceful failure handling for unexpected database errors
        return jsonify({"error": "Unable to process low stock alerts at this time."}), 500

def calculate_daily_sales(product_id, warehouse_id):
    # This is a helper function to aggregate sales over the last 30 days
    # In a live app, this would query the InventoryLedger table
    return 2.5 

if __name__ == '__main__':
    app.run(debug=True)
