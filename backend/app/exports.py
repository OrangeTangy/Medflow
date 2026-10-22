import io, csv

def csv_export(rows):
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['Doctor','Department','Location','First arrival (UTC)','Detected hours','Evidence status'])
    for d in rows:
        values=[d['full_name'],d['department'],d['location'] or 'Unknown',str(d['first_arrival'] or ''),d['hours'],d['status']]
        # Avoid spreadsheet formula execution from user-controlled text.
        writer.writerow(["'"+v if isinstance(v,str) and v[:1] in ('=','+','-','@','\t','\r') else v for v in values])
    return stream.getvalue()

def pdf_export(rows,date):
    lines=['Medflow - Hospital presence report',f'Date: {date} | All event timestamps: UTC','Device presence is not verified clinical work.','']
    for d in rows:lines.extend([d['full_name']+' | '+d['department'],f"{d['location'] or 'Unknown'} | {d['hours']:.2f} hours | {d['status']}",''])
    pages=[lines[i:i+45] for i in range(0,len(lines),45)] or [[]]
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    refs=[]
    for page in pages:
        pid=len(objects)+1;cid=pid+1;refs.append(f'{pid} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>'.encode())
        escape=lambda s:s.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        stream=('BT /F1 10 Tf 45 750 Td 15 TL '+' '.join(f'({escape(line)}) Tj T*' for line in page)+' ET').encode('latin-1','replace')
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects[1]=f'<< /Type /Pages /Count {len(pages)} /Kids [{" ".join(refs)}] >>'.encode()
    result=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(result));result+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(result);result+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
