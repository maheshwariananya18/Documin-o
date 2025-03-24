import os
import torch
import asyncio
from transformers import AutoTokenizer, AutoModel
from PIL import Image
import torchvision.transforms as T
from datetime import datetime

# Global variables for model and tokenizer
global_model = None
global_tokenizer = None

# Model configuration
MODEL_PATH = "OpenGVLab/InternVL2_5-1B"
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if torch.cuda.is_available() else torch.float32

# System instructions for different document types
passport_instruction = (
   "Extract the following specific data from this passport image. Look carefully for each field:"
"\n\n1. PASSPORT COUNTRY CODE: The 3-letter country code, usually in the MRZ or on the data page"
"\n\n2. PASSPORT TYPE: Usually a single letter (P for regular passport) in the MRZ line"
"\n\n3. PASSPORT NUMBER: Look for 'Passport No./No. du Passeport'"
"\n\n4. FIRST NAME: Extract only the first/given name from 'Given names/Prénoms'"
"\n\n5. FAMILY NAME: Extract only the surname/family name from 'Surname/Nom'"
"\n\n6. DATE OF BIRTH: Extract the day, month, and year separately"
"   - Date of Birth Day (numeric)"
"   - Date of Birth Month (numeric or text)"
"   - Date of Birth Year (4 digits)"
"\n\n7. PLACE OF BIRTH: Look for 'Place of birth/Lieu de naissance'"
"\n\n8. GENDER: Look for 'Sex/Sexe' field (M or F)"
"\n\n9. DATE OF ISSUE: Extract the day, month, and year separately"
"   - Date of Issue Day (numeric)"
"   - Date of Issue Month (numeric or text)"
"   - Date of Issue Year (4 digits)"
"\n\n10. DATE OF EXPIRATION: Extract the day, month, and year separately"
"   - Date of Expiration Day (numeric)"
"   - Date of Expiration Month (numeric or text)"
"   - Date of Expiration Year (4 digits)"
"\n\n11. ISSUING AUTHORITY: Agency or entity that issued the passport"
"\n\nOutput exactly in this format (write 'Not visible' only if you cannot find the information):"
"\n----------------------------"
"\nPassport Country Code: [3-letter code]"
"\nPassport Type: [letter code]"
"\nPassport Number: [number]"
"\nFirst Name: [first/given name only]"
"\nFamily Name: [family/surname only]"
"\nDate of Birth Day: [day]"
"\nDate of Birth Month: [month]"
"\nDate of Birth Year: [year]"
"\nPlace of Birth: [place]"
"\nGender: [M/F]"
"\nDate of Issue Day: [day]"
"\nDate of Issue Month: [month]"
"\nDate of Issue Year: [year]"
"\nDate of Expiration Day: [day]"
"\nDate of Expiration Month: [month]"
"\nDate of Expiration Year: [year]"
"\nAuthority: [issuing authority]"
)

check_instruction = (
   "Extract text exactly as it appears in this check/cheque image. Look carefully for ONLY these specific fields:"
"\n\n1. BANK NAME:"
"   - Look at the top center/header of check"
"   - Usually includes words like 'Bank', 'Trust', 'Financial' etc."
"\n\n2. PAYOR NAME:"
"   - Look for the pre-printed name at top-left of check"
"   - This is the person/entity WRITING the check"
"   - Extract only the name"
"\n\n3. PAYOR ADDRESS:"
"   - Look for the pre-printed address under the payor name"
"   - Include complete street address"
"\n\n4. CHECK NUMBER:"
"   - Look for number in top-right corner or bottom MICR line"
"\n\n5. PAYEE NAME:"
"   - Look for name after 'Pay to the order of' or 'Pay'"
"   - Extract only the name"
"   - If business name, include full name"
"\n\n6. PAYEE ADDRESS:"
"   - Look for address associated with payee if present"
"\n\n7. AMOUNT:"
"   - Look for amount in numbers (in box on right side)"
"   - Format as dollars and cents (e.g., 1,123.56)"
"\n\nOutput exactly in this format :"
"\n----------------------------"
"\nBank Name: [name of bank]"
"\n1st Payor First Name: [ name of payor]"
"\nPayor Street Address: [complete street address]"
"\nCheck Amount: [amount in numbers]"
"\n1st Payee First Name: [ name or business name]"
"\nCheck Number: [number]"
"\nPayee Street Address: [complete street address]"
)

invoice_instruction = (
   "Extract text exactly as it appears in this invoice image. For each field below:"
"\n\n1. INVOICE NUMBER: Look for 'Invoice #', 'Invoice Number', etc."
"\n\n2. INVOICE DATE: Look for 'Date', 'Invoice Date', etc."
"\n\n3. DUE DATE: Look for 'Due Date', 'Payment Due', etc."
"\n\n4. VENDOR/SELLER: Company name, address, contact info (who issued the invoice)"
"\n\n5. CUSTOMER/BILL TO: Name and address of the customer"
"\n\n6. PAYMENT TERMS: Look for 'Terms', 'Payment Terms', etc. (e.g., Net 30)"
"\n\n7. ITEMS/SERVICES: List all line items with descriptions, quantities, unit prices"
"\n\n8. SUBTOTAL: Amount before tax/shipping"
"\n\n9. TAX: Tax amount and rate (if specified)"
"\n\n10. SHIPPING/HANDLING: Shipping or handling charges (if any)"
"\n\n11. TOTAL AMOUNT: Final amount due"
"\n\n12. PAYMENT INSTRUCTIONS: Bank details, payment methods, etc."
"\n\nOutput exactly in this format (write 'Not visible' only if you cannot find the information):"
"\n----------------------------"
"\nInvoice Number: [number]"
"\nInvoice Date: [date]"
"\nDue Date: [date]"
"\nVendor/Seller: [company name & address]"
"\nCustomer: [name & address]"
"\nPayment Terms: [terms]"
"\nItems/Services: [description of items with prices]"
"\nSubtotal: [amount]"
"\nTax: [amount and rate]"
"\nShipping/Handling: [amount if applicable]"
"\nTotal Amount: [final amount]"
"\nPayment Instructions: [payment details]"
)

system_instructions = {
    "passport": passport_instruction,
    "check": check_instruction,
    "invoice": invoice_instruction
}

def fix_asyncio_event_loop():
    """Fix for asyncio event loop issues with Streamlit"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If there is no event loop in the current thread, create one
        asyncio.set_event_loop(asyncio.new_event_loop())

def load_model():
    """Load model with error handling"""
    global global_model, global_tokenizer
    
    try:
        # If model is already loaded, return the global instances
        if global_model is not None and global_tokenizer is not None:
            print("Using already loaded model and tokenizer")
            return global_tokenizer, global_model
            
        # Fix potential asyncio issues
        fix_asyncio_event_loop()
        
        print("Loading model for the first time...")
        
        # Initialize tokenizer with error handling
        global_tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True, use_fast=False)
        global_tokenizer.pad_token = global_tokenizer.eos_token

        # Load model with error handling
        global_model = AutoModel.from_pretrained(
            MODEL_PATH,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            do_sample=True
        ).to(device).eval()
        
        print("Model loaded successfully!")
        return global_tokenizer, global_model
    except Exception as e:
        error_msg = f"Error loading model: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg)

def preprocess_image(image_path, input_size=448, min_size=14):
    """Preprocess image with error handling"""
    try:
        image = Image.open(image_path)

        # Convert only if not already RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Get current image dimensions
        w, h = image.size
        
        # Ensure minimum dimensions while maintaining aspect ratio
        if w < min_size or h < min_size:
            scale = max(min_size/w, min_size/h)
            new_w = max(min_size, int(w * scale))
            new_h = max(min_size, int(h * scale))
            image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Create a square image by padding with white
        max_dim = max(image.size)
        square_size = max(max_dim, input_size)
        
        # Create a white background
        new_image = Image.new('RGB', (square_size, square_size), (255, 255, 255))
        
        # Paste the original image in the center
        paste_x = (square_size - w) // 2
        paste_y = (square_size - h) // 2
        new_image.paste(image, (paste_x, paste_y))
        
        # Now resize to input_size if necessary
        if square_size > input_size:
            new_image = new_image.resize((input_size, input_size), Image.Resampling.LANCZOS)
        
        # Convert to tensor and normalize
        transform = T.Compose([
            T.ToTensor(),
            T.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))
        ])
        
        return transform(new_image).unsqueeze(0).to(device, dtype=dtype)
    except Exception as e:
        error_msg = f"Error preprocessing image: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg)

def process_document_image(image_path, document_type, tokenizer, model):
    """Process a single document image and return extracted text"""
    try:
        # Fix potential asyncio issues
        fix_asyncio_event_loop()
        
        # Preprocess the image
        pixel_values = preprocess_image(image_path)
        
        # Get appropriate system instruction
        system_instruction = system_instructions.get(document_type, passport_instruction)
        
        # Create prompt
        prompt = f"<image>\n{system_instruction}\n\n"
        
        # Configure generation
        generation_config = dict(
            max_new_tokens=512, 
            pad_token_id=tokenizer.eos_token_id
        )
        
        # Get model response
        response = model.chat(
            tokenizer=tokenizer,
            pixel_values=pixel_values,
            question=prompt,
            generation_config=generation_config,
            history=None,
            return_history=False
        )
        
        return response
        
    except Exception as e:
        error_message = f"Error processing image: {str(e)}"
        print(error_message)
        return f"Error processing image: {str(e)}"

def process_multiple_images(image_folder, document_type="passport", output_file=None):
    # Supported image extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
    
    # Set default output file if not provided
    if output_file is None:
        output_file = f"{document_type}_extractions.txt"
    
    # Create output directory if needed
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Load model and tokenizer
    print("Loading model and tokenizer...")
    tokenizer, model = load_model()
    print("Model loaded successfully!")
    
    # Get all image files from the folder
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(image_extensions)]
    
    # Process each image and write results to the output file
    with open(output_file, 'w', encoding='utf-8') as out_file:
        out_file.write(f"{document_type.capitalize()} Data Extraction - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for i, filename in enumerate(image_files):
            image_path = os.path.join(image_folder, filename)
            print(f"Processing {i+1}/{len(image_files)}: {filename}")
            
            try:
                # Process the image
                response = process_document_image(image_path, document_type, tokenizer, model)
                
                # Write to file
                out_file.write(f"File: {filename}\n")
                out_file.write(f"{response}\n")
                out_file.write("-" * 50 + "\n\n")
                
                # Flush to ensure writing
                out_file.flush()
                
            except Exception as e:
                error_msg = f"Error processing {filename}: {str(e)}"
                print(error_msg)
                out_file.write(f"File: {filename}\n")
                out_file.write(f"ERROR: {str(e)}\n")
                out_file.write("-" * 50 + "\n\n")
                out_file.flush()
    
    print(f"Processing complete! Results saved to {output_file}")

def main():
    # Folder containing document images
    image_folder = "Documents"
    
    # Output file path
    output_file = "document_extraction_results.txt"
    
    # Process all images
    process_multiple_images(image_folder, "passport", output_file)

if __name__ == "__main__":
    main()