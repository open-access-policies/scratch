import os
import subprocess
import tempfile
import re
import yaml
import sys
import argparse
from collections import defaultdict


class MarkdownToPDFCompiler:
    def __init__(self, base_dir, force_overwrite=False):
        self.base_dir = base_dir
        self.force_overwrite = force_overwrite
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
    def extract_yaml_front_matter(self, content):
        """Extract YAML front matter from content and return a tuple of (front_matter_dict, remaining_content)"""
        if content.startswith('---'):
            end_index = content.find('---', 3)
            if end_index != -1:
                front_matter = content[3:end_index].strip()
                remaining_content = content[end_index+3:].strip()
                try:
                    front_matter_dict = yaml.safe_load(front_matter)
                    return front_matter_dict, remaining_content
                except yaml.YAMLError:
                    return {}, content
        return {}, content

    def ensure_proper_markdown_formatting(self, content):
        """Ensure markdown lists and other elements are properly formatted, but preserve table formatting"""
        lines = content.split('\n')
        is_table_line = [line.strip().startswith('|') and line.strip().endswith('|') for line in lines]
        
        result_lines = []
        i = 0
        while i < len(lines):
            if is_table_line[i]:
                # Handle table sections
                if i > 0 and not is_table_line[i-1] and result_lines and result_lines[-1].strip():
                    result_lines.append('')
                
                while i < len(lines) and is_table_line[i]:
                    result_lines.append(lines[i])
                    i += 1
                
                if i < len(lines) and not is_table_line[i] and lines[i].strip():
                    result_lines.append('')
            else:
                # Handle non-table content
                line = lines[i]
                
                if (line.strip().startswith('- ') and i > 0 and result_lines and 
                    result_lines[-1].strip() and not result_lines[-1].strip().startswith('- ')):
                    result_lines.append('')
                
                result_lines.append(line)
                
                if (line.strip().startswith('- ') and i < len(lines) - 1 and 
                    not lines[i+1].strip().startswith('- ') and lines[i+1].strip()):
                    result_lines.append('')
                
                i += 1
        
        content = '\n'.join(result_lines)
        content = re.sub(r'<!--.*?-->\s*\n- ', r'\n\n- ', content)
        return content

    def is_test_file(self, content):
        """Check if content indicates this is a test file that should be skipped"""
        test_indicators = ['doctest:', 'Extension:', '# Preamble']
        return any(indicator in content[:512] for indicator in test_indicators)

    def collect_markdown_files(self):
        """Collect and process markdown files from subdirectories starting with underscore"""
        md_files = []
        for root, dirs, files in os.walk(self.base_dir):
            if root == self.base_dir:
                continue
            
            dir_name = os.path.basename(root)
            if not dir_name.startswith('_'):
                continue
                
            for file in sorted(files):
                if file.endswith('.md'):
                    filepath = os.path.join(root, file)
                    file_data = self.process_markdown_file(filepath)
                    if file_data:
                        md_files.append(file_data)
        
        return sorted(md_files, key=lambda x: (x['parent'], x['nav_order']))

    def process_markdown_file(self, filepath):
        """Process a single markdown file and return its data if valid"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                if self.is_test_file(content):
                    print(f"Skipping test file: {filepath}")
                    return None
                
                front_matter, content_without_front_matter = self.extract_yaml_front_matter(content)
                content_without_front_matter = self.ensure_proper_markdown_formatting(content_without_front_matter)
                
                if 'title' in front_matter and 'parent' in front_matter:
                    return {
                        'filepath': filepath,
                        'title': front_matter.get('title', ''),
                        'parent': front_matter.get('parent', ''),
                        'nav_order': front_matter.get('nav_order', 999),
                        'content': content_without_front_matter
                    }
        except Exception as e:
            print(f"Could not read file {filepath}: {e}")
        return None

    def generate_custom_toc(self, md_files):
        """Generate a custom table of contents grouped by parent category"""
        toc = "# Table of Contents\n\n"
        
        parent_groups = defaultdict(list)
        for file in md_files:
            parent_groups[file['parent']].append(file)
        
        for parent, files in sorted(parent_groups.items()):
            escaped_parent = parent.replace('&', '\\&')
            toc += f"## {escaped_parent}\n\n"
            for file in files:
                anchor = file['title'].lower().replace(' ', '-').replace('(', '').replace(')', '').replace(',', '').replace('&', '')
                escaped_file_title = file['title'].replace('&', '\\&')
                toc += f"- [{escaped_file_title}](#{anchor})\n"
            toc += "\n"
        
        toc += "\n\\newpage\n\n"
        return toc

    def get_title_from_index(self):
        """Extract title from index.md file in the base directory"""
        index_path = os.path.join(self.base_dir, 'index.md')
        
        if not os.path.exists(index_path):
            print(f"Warning: index.md not found in {self.base_dir}")
            return "Document Collection"
        
        try:
            with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                front_matter, _ = self.extract_yaml_front_matter(content)
                
                if 'title' in front_matter:
                    return front_matter['title']
                else:
                    print("Warning: No title found in index.md front matter")
                    return "Document Collection"
                    
        except Exception as e:
            print(f"Error reading index.md: {e}")
            return "Document Collection"

    def generate_title_page(self, title):
        """Generate a title page with the given title and subheading"""
        latex_safe_title = title.replace('&', '\\&')
        
        return f"""\\begin{{titlepage}}
\\centering
\\vspace*{{\\fill}}

{{\\Huge\\bfseries {latex_safe_title} \\par}}

\\vspace{{2cm}}

{{\\Large openaccesspolicies.org \\par}}

\\vspace*{{\\fill}}

\\vfill
{{\\footnotesize CC-BY-SA-4.0 Licensed \\par}}

\\end{{titlepage}}

\\newpage

"""

    def escape_latex_special_chars(self, content):
        """Escape special LaTeX characters that might cause compilation errors"""
        lines = content.split('\n')
        result_lines = []
        
        for line in lines:
            if line.strip().startswith('|') and line.strip().endswith('|'):
                result_lines.append(line)
            else:
                line = line.replace('&', '\\&')
                result_lines.append(line)
        
        return '\n'.join(result_lines)

    def create_temp_markdown(self, md_files, title):
        """Create temporary markdown file with all content"""
        temp_md = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.md', encoding='utf-8')
        
        # Write title page
        title_page = self.generate_title_page(title)
        temp_md.write(title_page)
        
        # Write TOC
        custom_toc = self.generate_custom_toc(md_files)
        temp_md.write(custom_toc)
        
        # Write content
        for i, file_info in enumerate(md_files):
            escaped_title = self.escape_latex_special_chars(file_info['title'])
            temp_md.write(f"# {escaped_title}\n\n")
            
            escaped_content = self.escape_latex_special_chars(file_info['content'])
            temp_md.write(escaped_content)
            
            if i < len(md_files) - 1:
                temp_md.write("\n\n\\newpage\n\n")
        
        temp_md.close()
        return temp_md.name

    def build_pandoc_command(self, temp_md_path, output_pdf_path):
        """Build the pandoc command with all necessary arguments"""
        return [
            'pandoc', temp_md_path, '-o', output_pdf_path,
            '--pdf-engine=xelatex',
            '--highlight-style', 'tango',
            '-V', 'geometry:margin=1in',
            '-V', 'fontsize=11pt',
            '-V', 'documentclass=article',
            '-V', 'mainfont=Charter',
            '-V', 'linestretch=1.4',
            '--standalone',
            '-f', 'markdown+pipe_tables',
            '--wrap=preserve',
            f'--resource-path={self.script_dir}',
            f'--include-in-header={os.path.join(self.script_dir, "preamble.tex")}',
            f'--include-before-body={os.path.join(self.script_dir, "header.tex")}',
        ]

    def compile_with_pandoc(self, md_files, output_pdf_path, title):
        """Compile markdown files to PDF using pandoc"""
        temp_md_path = self.create_temp_markdown(md_files, title)
        cmd = self.build_pandoc_command(temp_md_path, output_pdf_path)

        try:
            subprocess.run(cmd, check=True)
            print(f'PDF created: {output_pdf_path}')
            print(f'Created and processed temporary markdown file: {temp_md_path}')
        except Exception as e:
            print(f"Error generating PDF: {e}")
            print(f"Temporary markdown file: {temp_md_path}")
        finally:
            if os.path.exists(temp_md_path):
                os.remove(temp_md_path)
                print(f"Removed temporary file: {temp_md_path}")

    def get_output_path(self):
        """Determine output file path and handle existing files"""
        dir_name = os.path.basename(os.path.abspath(self.base_dir))
        if not dir_name:
            dir_name = os.path.basename(os.path.dirname(os.path.abspath(self.base_dir)))
        
        assets_dir = os.path.join(self.base_dir, 'assets', 'files')
        os.makedirs(assets_dir, exist_ok=True)
        
        base_filename = f'{dir_name}_compiled.pdf'
        output_file = os.path.join(assets_dir, base_filename)
        
        return self.handle_existing_file(output_file, dir_name)

    def handle_existing_file(self, output_file, dir_name):
        """Handle existing output files based on force flag or user input"""
        if os.path.exists(output_file) and not self.force_overwrite:
            print(f"File already exists: {output_file}")
            while True:
                choice = input("Would you like to (o)verwrite, (r)ename, or (c)ancel? ").strip().lower()
                if choice in ['o', 'overwrite']:
                    break
                elif choice in ['r', 'rename']:
                    new_name = input(f"Enter new filename (without .pdf extension, current: {dir_name}_compiled): ").strip()
                    if new_name:
                        assets_dir = os.path.dirname(output_file)
                        new_output_file = os.path.join(assets_dir, f'{new_name}.pdf')
                        if os.path.exists(new_output_file):
                            print(f"File {new_output_file} also exists. Please choose a different name.")
                            continue
                        return new_output_file
                    else:
                        print("Please enter a valid filename.")
                elif choice in ['c', 'cancel']:
                    print("Operation cancelled.")
                    sys.exit(0)
                else:
                    print("Please enter 'o' for overwrite, 'r' for rename, or 'c' for cancel.")
        elif os.path.exists(output_file) and self.force_overwrite:
            print(f"Overwriting existing file: {output_file}")
        
        return output_file

    def compile(self):
        """Main compilation method"""
        document_title = self.get_title_from_index()
        output_file = self.get_output_path()
        
        print(f"Processing directory: {self.base_dir}")
        print(f"Document title: {document_title}")
        print(f"Output file will be: {output_file}")
        
        markdown_files = self.collect_markdown_files()
        
        if not markdown_files:
            print("No markdown files found in subdirectories.")
        else:
            self.compile_with_pandoc(markdown_files, output_file, document_title)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Compile markdown files to PDF')
    parser.add_argument('base_dir', nargs='?', help='Base directory containing markdown files')
    parser.add_argument('-f', '--force', action='store_true', help='Overwrite existing output file without prompting')
    return parser.parse_args()


def get_base_directory(args):
    """Get base directory from arguments or user input"""
    if args.base_dir:
        return args.base_dir.strip()
    else:
        base_dir = input("Enter the base directory path: ").strip()
        return base_dir if base_dir else './'


if __name__ == '__main__':
    args = parse_arguments()
    base_dir = get_base_directory(args)
    
    compiler = MarkdownToPDFCompiler(base_dir, args.force)
    compiler.compile()
