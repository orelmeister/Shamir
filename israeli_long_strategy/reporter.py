from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import logging
import os
try:
    from bidi.algorithm import get_display
    import arabic_reshaper
    HAS_RTL_SUPPORT = True
except ImportError:
    HAS_RTL_SUPPORT = False

logger = logging.getLogger(__name__)

class RiskReporter:
    def __init__(self, output_path: str = "Israeli_Long_Opportunity_Report.pdf"):
        self.output_path = output_path
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        self._register_fonts()

    def _register_fonts(self):
        """Register fonts that support Hebrew"""
        try:
            # Try standard Windows Arial
            font_path = "C:/Windows/Fonts/arial.ttf"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Arial', font_path))
                self.hebrew_font = 'Arial'
            else:
                # Fallback or warning
                logger.warning("Arial font not found. Hebrew PDF may not render correctly.")
                self.hebrew_font = 'Helvetica' # Won't work for Hebrew but prevents crash
        except Exception as e:
            logger.error(f"Font registration failed: {e}")
            self.hebrew_font = 'Helvetica'

    def _setup_styles(self):
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1 # Center
        )
        self.h2_style = ParagraphStyle(
            'CustomH2',
            parent=self.styles['Heading2'],
            fontSize=18,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.darkred
        )
        self.normal_style = self.styles['Normal']
        
        # Hebrew Styles
        self.he_normal_style = ParagraphStyle(
            'HebrewNormal',
            parent=self.styles['Normal'],
            fontName='Arial',
            fontSize=10,
            leading=14,
            alignment=2 # Right alignment for RTL
        )
        self.he_h2_style = ParagraphStyle(
            'HebrewH2',
            parent=self.styles['Heading2'],
            fontName='Arial',
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.darkred,
            alignment=2
        )

    def _make_rtl(self, text):
        """Reshape and reverse text for RTL display"""
        if not HAS_RTL_SUPPORT:
            return text
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text

    def generate_report(self, analysis_results: dict):
        """Generate PDF report from analysis results"""
        logger.info(f"📄 Generating report: {self.output_path}")
        
        doc = SimpleDocTemplate(self.output_path, pagesize=letter)
        story = []
        
        # 1. Title
        story.append(Paragraph("Israeli Long Opportunity Report", self.title_style))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", self.normal_style))
        story.append(Spacer(1, 20))
        
        # 2. Executive Summary (Top Shorts)
        story.append(Paragraph("✅ Top Long Candidates", self.h2_style))
        
        top_candidates = analysis_results.get("top_long_candidates", [])
        if not top_candidates:
            story.append(Paragraph("No high-conviction long candidates found.", self.normal_style))
        else:
            # Table Data
            data = [["Symbol", "Bucket", "Score", "Recommendation"]]
            for c in top_candidates[:5]: # Top 5
                data.append([
                    c['symbol'], 
                    (c.get('bucket') or '').title(), 
                    f"{c['long_score']:.1f}/100", 
                    c['recommendation']
                ])
            
            # Table Style
            t = Table(data, colWidths=[100, 100, 80, 150])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(t)
            
        story.append(Spacer(1, 20))
        
        # 3. Detailed Sector Analysis
        story.append(Paragraph("🔍 Deep Dive", self.h2_style))
        
        for bucket, companies in analysis_results.get("bucket_analysis", {}).items():
            story.append(Paragraph(f"Bucket: {bucket.upper()}", self.styles['Heading3']))
            
            for co in companies:
                # Company Header
                story.append(Paragraph(f"<b>{co['symbol']}</b> - Score: {co['long_score']:.1f}", self.normal_style))
                
                # Source Link
                yahoo_url = f"https://finance.yahoo.com/quote/{co['symbol']}"
                story.append(Paragraph(f'<a href="{yahoo_url}" color="blue"><u>Source: Yahoo Finance Data ({co["symbol"]})</u></a>', self.normal_style))
                
                # Reasoning (English)
                fin_txt = f"<b>Fundamental (DeepSeek):</b> {co['details'].get('fundamental_reasoning_en', 'N/A')}"
                macro_txt = f"<b>Macro (Gemini):</b> {co['details'].get('macro_reasoning_en', 'N/A')}"
                
                story.append(Paragraph(fin_txt, self.normal_style))
                story.append(Paragraph(macro_txt, self.normal_style))
                
                story.append(Spacer(1, 10))
                
        # 4. Disclaimer
        story.append(Spacer(1, 30))
        disclaimer = """
        <b>DISCLAIMER:</b> This report is generated by AI agents for informational purposes only. 
        It does not constitute financial advice. Shorting stocks involves infinite risk. 
        Verify product suitability (including kosher/halachic compliance) with your own rabbinic authority and fund documentation.
        """
        story.append(Paragraph(disclaimer, self.styles['Italic']))
        
        doc.build(story)
        logger.info("✅ PDF Report generated successfully.")
        
        # Generate Hebrew Report
        self.generate_hebrew_report(analysis_results)

    def generate_hebrew_report(self, analysis_results: dict):
        """Generate a PDF report in Hebrew"""
        he_path = self.output_path.replace(".pdf", "_HE.pdf")
        logger.info(f"📄 Generating Hebrew PDF report: {he_path}")
        
        doc = SimpleDocTemplate(he_path, pagesize=letter)
        story = []
        
        # 1. Title
        title_text = self._make_rtl("דוח הזדמנויות לונג - ישראל")
        story.append(Paragraph(title_text, self.title_style))
        
        date_text = self._make_rtl(f"תאריך: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        story.append(Paragraph(date_text, self.he_normal_style))
        story.append(Spacer(1, 20))
        
        # 2. Executive Summary
        header_text = self._make_rtl("מועמדים מובילים ללונג")
        story.append(Paragraph(f"✅ {header_text}", self.he_h2_style))
        
        top_candidates = analysis_results.get("top_long_candidates", [])
        if not top_candidates:
            no_cand_text = self._make_rtl("לא נמצאו מועמדים בעלי סבירות גבוהה ללונג.")
            story.append(Paragraph(no_cand_text, self.he_normal_style))
        else:
            # Table Data (Headers in Hebrew)
            headers = [
                self._make_rtl("סימול"),
                self._make_rtl("סקטור"),
                self._make_rtl("ציון"),
                self._make_rtl("המלצה")
            ]
            data = [headers]
            for c in top_candidates[:5]:
                data.append([
                    c['symbol'], 
                    self._make_rtl(c.get('bucket', c.get('sector', ''))), 
                    f"{c['long_score']:.1f}", 
                    self._make_rtl(c['recommendation'])
                ])
            
            t = Table(data, colWidths=[80, 100, 60, 150])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Arial'), # Use Hebrew font
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(t)
            
        story.append(Spacer(1, 20))
        
        # 3. Detailed Sector Analysis
        sector_header = self._make_rtl("ניתוח מעמיק לפי סקטורים")
        story.append(Paragraph(f"🔍 {sector_header}", self.he_h2_style))
        
        for bucket, companies in analysis_results.get("bucket_analysis", {}).items():
            sec_text = self._make_rtl(f"קטגוריה: {bucket}")
            story.append(Paragraph(sec_text, self.he_h2_style))
            
            for co in companies:
                # Company Header
                story.append(Paragraph(f"<b>{co['symbol']}</b> - Score: {co['long_score']:.1f}", self.normal_style))
                
                # Reasoning (Hebrew)
                fin_reason = co['details'].get('fundamental_reasoning_he', co['details'].get('fundamental_reasoning_en', 'N/A'))
                macro_reason = co['details'].get('macro_reasoning_he', co['details'].get('macro_reasoning_en', 'N/A'))
                
                fin_txt = self._make_rtl(f"פיננסי: {fin_reason}")
                macro_txt = self._make_rtl(f"מאקרו: {macro_reason}")
                
                story.append(Paragraph(fin_txt, self.he_normal_style))
                story.append(Paragraph(macro_txt, self.he_normal_style))
                
                story.append(Spacer(1, 10))
                
        doc.build(story)
        logger.info("✅ Hebrew PDF Report generated successfully.")


if __name__ == "__main__":
    # Test
    reporter = RiskReporter()
    reporter.generate_report({"top_long_candidates": []})
