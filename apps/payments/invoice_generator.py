from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.conf import settings
from io import BytesIO
from datetime import datetime


class InvoiceGenerator:
    """Multi-platform invoice generator"""
    
    def __init__(self, platform=None):
        self.platform = platform
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        # Use platform colors if available
        primary_color = '#2563eb'
        if self.platform and hasattr(self.platform, 'primary_color'):
            primary_color = self.platform.primary_color or primary_color
        
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor(primary_color),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Normal'],
            fontSize=18,
            textColor=colors.HexColor('#1e40af'),
            fontName='Helvetica-Bold',
            spaceAfter=10
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#374151'),
            fontName='Helvetica-Bold',
            spaceAfter=10,
            spaceBefore=20
        ))

    def generate_invoice(self, payment):
        """Generate invoice PDF for payment with multiple webinars"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            rightMargin=72, 
            leftMargin=72,
            topMargin=72, 
            bottomMargin=18
        )
        
        elements = []
        
        # Add header with platform branding
        self.add_header(elements)
        
        # Add invoice title and number
        self.add_invoice_title(elements, payment)
        
        # Add billing information
        self.add_billing_info(elements, payment.user, payment)
        
        # Add webinar details (support multiple webinars)
        self.add_webinar_details(elements, payment)
        
        # Add payment summary
        self.add_payment_summary(elements, payment)
        
        # Add footer
        self.add_footer(elements)
        
        # Build PDF
        doc.build(elements)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        return pdf

    def add_header(self, elements):
        """Platform-branded header"""
        platform_name = self.platform.name if self.platform else "WebinarPro"
        support_email = self.platform.support_email if self.platform else "support@webinarpro.com"
        
        header_data = [
            [
                Paragraph(f'<font color="#2563eb" size="20"><b>{platform_name}</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#6b7280" size="10">Professional Webinar Platform<br/>{support_email}<br/>Invoice & Receipt</font>', self.styles['Normal'])
            ]
        ]
        
        header_table = Table(header_data, colWidths=[3*inch, 3*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#e5e7eb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        elements.append(header_table)
        elements.append(Spacer(1, 30))

    def add_invoice_title(self, elements, payment):
        """Invoice title with number"""
        title = Paragraph('<font color="#dc2626" size="28"><b>INVOICE</b></font>', self.styles['CustomTitle'])
        elements.append(title)
        
        invoice_number = payment.invoice_display_number
        
        invoice_data = [
            [
                Paragraph('<font color="#374151"><b>Invoice Number:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{invoice_number}</font>', self.styles['Normal'])
            ],
            [
                Paragraph('<font color="#374151"><b>Invoice Date:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{payment.created_at.strftime("%B %d, %Y")}</font>', self.styles['Normal'])
            ],
            [
                Paragraph('<font color="#374151"><b>Payment Status:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#059669"><b>{payment.get_status_display().upper()}</b></font>', self.styles['Normal'])
            ]
        ]
        
        invoice_table = Table(invoice_data, colWidths=[2*inch, 2*inch])
        invoice_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#10b981')),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        elements.append(invoice_table)
        elements.append(Spacer(1, 30))

    def add_billing_info(self, elements, user, payment):
        """Billing information"""
        billing_title = Paragraph(
            '<font color="#7c3aed" size="16"><b>Billing Information</b></font>', 
            self.styles['SectionHeader']
        )
        elements.append(billing_title)
        
        billing_data = [
            [
                Paragraph('<font color="#374151"><b>Customer Name:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{user.get_full_name() or user.email}</font>', self.styles['Normal'])
            ],
            [
                Paragraph('<font color="#374151"><b>Email:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{user.email}</font>', self.styles['Normal'])
            ],
            [
                Paragraph('<font color="#374151"><b>Transaction ID:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{payment.transaction_id}</font>', self.styles['Normal'])
            ],
            [
                Paragraph('<font color="#374151"><b>Payment Method:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{payment.get_payment_method_display()}</font>', self.styles['Normal'])
            ]
        ]
        
        if self.platform:
            billing_data.append([
                Paragraph('<font color="#374151"><b>Platform:</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#1f2937">{self.platform.name}</font>', self.styles['Normal'])
            ])
        
        billing_table = Table(billing_data, colWidths=[2*inch, 4*inch])
        billing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#faf5ff')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#c084fc')),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(billing_table)
        elements.append(Spacer(1, 20))

    def add_webinar_details(self, elements, payment):
        """Webinar details - supports multiple webinars"""
        webinar_title = Paragraph(
            '<font color="#ea580c" size="16"><b>Webinar Details</b></font>', 
            self.styles['SectionHeader']
        )
        elements.append(webinar_title)
        
        # Build table data
        webinar_data = [['Item', 'Access Type', 'Amount']]
        
        # Get all payment webinars
        for pw in payment.payment_webinars.all():
            webinar_data.append([
                Paragraph(f'<font color="#1f2937"><b>{pw.webinar.title}</b></font>', self.styles['Normal']),
                Paragraph(f'<font color="#4b5563">{pw.access_type}</font>', self.styles['Normal']),
                Paragraph(f'<font color="#059669"><b>${pw.amount}</b></font>', self.styles['Normal'])
            ])
        
        webinar_table = Table(webinar_data, colWidths=[3.5*inch, 1.5*inch, 1*inch])
        webinar_table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fed7aa')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#9a3412')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            
            # Data rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fff7ed')),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#fb923c')),
            ('INNERGRID', (0, 0), (-1, -1), 1, colors.HexColor('#fed7aa')),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            
            # Alignment
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ]))
        
        elements.append(webinar_table)
        elements.append(Spacer(1, 20))

    def add_payment_summary(self, elements, payment):
        """Payment summary"""
        summary_title = Paragraph(
            '<font color="#059669" size="16"><b>Payment Summary</b></font>', 
            self.styles['SectionHeader']
        )
        elements.append(summary_title)
        
        subtotal = payment.amount
        
        summary_data = [
            ['', 'Subtotal:', f'${payment.currency} {subtotal:.2f}'],
            ['', '', ''],
            [
                '', 
                Paragraph('<font color="#059669" size="14"><b>Total Paid:</b></font>', self.styles['Normal']), 
                Paragraph(f'<font color="#059669" size="16"><b>${payment.currency} {subtotal:.2f}</b></font>', self.styles['Normal'])
            ]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch, 1*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#d1fae5')),
            ('BOX', (1, 0), (-1, 2), 2, colors.HexColor('#10b981')),
            ('LINEBELOW', (1, 1), (-1, 1), 2, colors.HexColor('#10b981')),
            ('LEFTPADDING', (1, 0), (-1, -1), 15),
            ('TOPPADDING', (1, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (1, 0), (-1, -1), 8),
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 30))

    def add_footer(self, elements):
        """Footer with platform info"""
        platform_name = self.platform.name if self.platform else "WebinarPro"
        support_email = self.platform.support_email if self.platform else "support@webinarpro.com"
        
        footer_text = f'''
        <font color="#059669" size="14"><b>Thank you for your business!</b></font><br/><br/>
        <font color="#6b7280" size="10">
        <b>Terms & Conditions:</b><br/>
        • Payment is due immediately upon registration<br/>
        • Refunds are available up to 24 hours before the webinar start time<br/>
        • Access details will be sent to your registered email address<br/>
        • For support, contact us at {support_email}<br/><br/>
        
        <b>{platform_name}</b> - Empowering Knowledge Through Technology
        </font>
        '''
        
        footer_para = Paragraph(footer_text, self.styles['Normal'])
        
        footer_table = Table([[footer_para]], colWidths=[6*inch])
        footer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9fafb')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        elements.append(footer_table)


# Usage in views
def generate_invoice_pdf(payment_id):
    """Generate invoice PDF for a payment"""
    from .models import Payment
    
    payment = Payment.objects.select_related('user', 'platform').get(id=payment_id)
    
    generator = InvoiceGenerator(platform=payment.platform)
    pdf_content = generator.generate_invoice(payment)
    
    return pdf_content
