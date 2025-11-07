"""
Email Sender Service - SendGrid Version
Alternative email service using SendGrid API for better Render compatibility

SendGrid is more reliable on cloud platforms like Render because:
- Uses HTTPS/API instead of SMTP (no port blocking)
- Better deliverability rates
- More reliable on cloud infrastructure
- Free tier: 100 emails/day

Setup:
1. Sign up at https://sendgrid.com/
2. Create API key: Settings > API Keys > Create API Key
3. Set environment variable: SENDGRID_API_KEY=your_key_here
4. Verify sender email in SendGrid dashboard
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from groq import Groq
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Load environment variables
load_dotenv()

class EmailRecipient(BaseModel):
    """Email recipient model"""
    name: str = Field(..., description="Recipient name")
    email: str = Field(..., description="Recipient email address")
    personal_description: str = Field(..., description="Personal interests and preferences")

class EmailCampaignRequest(BaseModel):
    """Email campaign request model"""
    company_name: str = Field(..., description="Company name")
    campaign_description: str = Field(..., description="Campaign description")
    recipients: List[EmailRecipient] = Field(..., description="List of email recipients")
    sender_name: Optional[str] = Field(None, description="Sender name (defaults to company name)")
    email_subject: Optional[str] = Field(None, description="Email subject (defaults to 'Special Offer from {company_name}!')")

class EmailDeliveryStatus(BaseModel):
    """Email delivery status model"""
    recipient_name: str = Field(..., description="Recipient name")
    recipient_email: str = Field(..., description="Recipient email")
    status: str = Field(..., description="Delivery status: 'sent', 'failed'")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    email_content: Optional[str] = Field(None, description="Generated email content")

class EmailCampaignResponse(BaseModel):
    """Email campaign response model"""
    campaign_summary: Dict[str, Any] = Field(..., description="Campaign summary")
    delivery_results: List[EmailDeliveryStatus] = Field(..., description="Email delivery results")
    execution_status: str = Field(..., description="Execution status: 'success', 'partial_success', 'failed'")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")

def send_email_campaign_sendgrid(request: EmailCampaignRequest) -> EmailCampaignResponse:
    """
    Send personalized email campaign using SendGrid API
    
    This function uses SendGrid's API (not SMTP) which works better on cloud platforms
    like Render where SMTP ports might be blocked.
    
    Args:
        request (EmailCampaignRequest): Email campaign request
    
    Returns:
        EmailCampaignResponse: Campaign results with delivery status
    """
    print(f"📧 Starting SendGrid email campaign for {request.company_name}")
    print(f"📝 Campaign: {request.campaign_description}")
    print(f"👥 Recipients: {len(request.recipients)}")
    
    # Check if recipients list is empty
    if not request.recipients or len(request.recipients) == 0:
        print("⚠️ No recipients provided. Returning empty campaign response.")
        return EmailCampaignResponse(
            campaign_summary={
                "company_name": request.company_name,
                "campaign_description": request.campaign_description,
                "total_recipients": 0,
                "successful_sends": 0,
                "failed_sends": 0,
                "success_rate": 0,
                "sender_name": request.sender_name or request.company_name,
                "sender_email": "N/A",
                "warning": "No recipients provided"
            },
            delivery_results=[],
            execution_status="failed",
            timestamp=datetime.now()
        )
    
    # Get credentials with detailed logging
    sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")
    groq_api_key = os.getenv("GROQ_API_KEY")
    sender_name = request.sender_name or os.getenv("SENDER_NAME", request.company_name)
    
    print(f"🔍 Environment check:")
    print(f"   SENDGRID_API_KEY: {'✓ Set' if sendgrid_api_key else '✗ Missing'}")
    print(f"   SENDER_EMAIL: {'✓ Set' if sender_email else '✗ Missing'}")
    print(f"   GROQ_API_KEY: {'✓ Set' if groq_api_key else '✗ Missing'}")
    print(f"   SENDER_NAME: {sender_name}")
    
    if not sendgrid_api_key:
        error_msg = "❌ Missing SENDGRID_API_KEY in environment variables.\n"
        error_msg += "   Get your API key from: https://app.sendgrid.com/settings/api_keys"
        print(error_msg)
        raise ValueError(error_msg)
    
    if not sender_email:
        error_msg = "❌ Missing SENDER_EMAIL in environment variables."
        print(error_msg)
        raise ValueError(error_msg)
    
    if not groq_api_key:
        error_msg = "❌ Missing GROQ_API_KEY in environment variables."
        print(error_msg)
        raise ValueError(error_msg)
    
    # Initialize clients
    try:
        groq_client = Groq(api_key=groq_api_key)
        print("✅ Groq client initialized successfully")
    except Exception as e:
        error_msg = f"❌ Failed to initialize Groq client: {str(e)}"
        print(error_msg)
        raise ValueError(error_msg)
    
    try:
        sg_client = SendGridAPIClient(sendgrid_api_key)
        print("✅ SendGrid client initialized successfully")
    except Exception as e:
        error_msg = f"❌ Failed to initialize SendGrid client: {str(e)}"
        print(error_msg)
        raise ValueError(error_msg)
    
    # Track delivery results
    delivery_results = []
    successful_sends = 0
    failed_sends = 0
    
    # Send emails using SendGrid API
    print(f"📬 Using SendGrid API for email delivery...")
    
    for recipient in request.recipients:
        try:
            print(f"📧 Generating email for {recipient.name}...")
            
            # Generate personalized email content using Groq
            prompt = f"""
            You are an expert advertising copywriter for {request.company_name}.
            Write a personalized, friendly, and persuasive marketing email for a campaign.
            
            Campaign Description:
            {request.campaign_description}

            Recipient Details:
            Name: {recipient.name}
            Interests and Preferences: {recipient.personal_description}

            Guidelines:
            - Keep it under 100 words.
            - Make it conversational and emotionally engaging.
            - Highlight how this offer or campaign benefits the recipient personally.
            - End with a warm closing from {request.company_name}.
            """
            
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}]
                )
                email_content = response.choices[0].message.content.strip()
                print(f"✅ Email content generated ({len(email_content)} chars)")
            except Exception as groq_error:
                error_msg = f"❌ Groq API error: {str(groq_error)}"
                print(error_msg)
                raise Exception(error_msg)
            
            # Create SendGrid message
            subject = request.email_subject or f"Special Offer from {request.company_name}!"
            
            message = Mail(
                from_email=Email(sender_email, sender_name),
                to_emails=To(recipient.email, recipient.name),
                subject=subject,
                plain_text_content=Content("text/plain", email_content)
            )
            
            # Send email via SendGrid API
            print(f"📤 Sending email to {recipient.email} via SendGrid...")
            try:
                response = sg_client.send(message)
                
                if response.status_code in [200, 201, 202]:
                    print(f"✅ Email sent successfully to {recipient.name}")
                    
                    delivery_results.append(EmailDeliveryStatus(
                        recipient_name=recipient.name,
                        recipient_email=recipient.email,
                        status="sent",
                        error_message=None,
                        email_content=email_content
                    ))
                    
                    successful_sends += 1
                else:
                    error_msg = f"SendGrid API returned status {response.status_code}"
                    print(f"❌ {error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as send_error:
                error_msg = f"❌ Failed to send via SendGrid: {str(send_error)}"
                print(error_msg)
                raise Exception(error_msg)
            
        except Exception as e:
            # Track failed delivery
            error_detail = str(e)
            print(f"❌ Failed to send email to {recipient.name} ({recipient.email}): {error_detail}")
            
            delivery_results.append(EmailDeliveryStatus(
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                status="failed",
                error_message=error_detail,
                email_content=None
            ))
            
            failed_sends += 1
            continue
    
    # Determine execution status
    if successful_sends == len(request.recipients):
        execution_status = "success"
    elif successful_sends > 0:
        execution_status = "partial_success"
    else:
        execution_status = "failed"
    
    # Create campaign summary
    campaign_summary = {
        "company_name": request.company_name,
        "campaign_description": request.campaign_description,
        "total_recipients": len(request.recipients),
        "successful_sends": successful_sends,
        "failed_sends": failed_sends,
        "success_rate": round((successful_sends / len(request.recipients)) * 100, 2) if request.recipients else 0,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "email_provider": "SendGrid API"
    }
    
    # Create response
    response = EmailCampaignResponse(
        campaign_summary=campaign_summary,
        delivery_results=delivery_results,
        execution_status=execution_status,
        timestamp=datetime.now()
    )
    
    print(f"✅ Email campaign completed: {successful_sends}/{len(request.recipients)} emails sent successfully")
    return response


if __name__ == "__main__":
    # Example usage
    print("SendGrid Email Sender - Test Mode")
    print("=" * 60)
    
    example_request = EmailCampaignRequest(
        company_name="GhejjMaxxers",
        campaign_description="Testing SendGrid integration for CampaignAI",
        recipients=[
            EmailRecipient(
                name="Test User",
                email="test@example.com",
                personal_description="interested in AI and automation"
            )
        ],
        sender_name="GhejjMaxxers Team",
        email_subject="Test Email via SendGrid"
    )
    
    try:
        result = send_email_campaign_sendgrid(example_request)
        print(f"\n✅ Campaign Status: {result.execution_status}")
        print(f"✅ Success Rate: {result.campaign_summary['success_rate']}%")
    except Exception as e:
        print(f"\n❌ Error: {e}")
