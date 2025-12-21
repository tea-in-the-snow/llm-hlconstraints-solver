"""
Python wrapper for Java Type Parse Service via CLI.
Provides easy-to-use Python interface for calling the Java type parsing utilities.
"""

import json
import subprocess
import os
import re
from typing import Dict, List, Optional
from config import JAVA_UTILS_PATH, CLASS_PATH


class TypeInfo:
    """Python representation of TypeInfoJson from Java"""
    
    def __init__(self, data: dict):
        self.data = data
        self.type_name = data.get('typeName')
        self.class_type = data.get('classType')
        self.super_class_name = data.get('superClassName')
        self.sub_class_names = data.get('subClassName', [])
        self.interfaces = data.get('interfaces', [])
        self.sub_interface_names = data.get('subInterfaceName', [])
        self.implemented_class_names = data.get('implementedClassName', [])
        self.fields = data.get('fields', {})
        self.constructors = data.get('constructors', {})
        self.builders = data.get('builders', {})
        self.methods = data.get('methods', [])
        self.inner_class_name = data.get('innerClassName')
        self.dimension = data.get('dimension')
    
    def is_interface(self) -> bool:
        return self.class_type == 'interface'
    
    def is_abstract(self) -> bool:
        return self.class_type == 'abstract class'
    
    def is_concrete_class(self) -> bool:
        return self.class_type == 'class'
    
    def is_array(self) -> bool:
        return self.class_type == 'array'
    
    def is_primitive(self) -> bool:
        return self.class_type == 'primitive'
    
    def get_constructor_signatures(self) -> List[str]:
        return list(self.constructors.keys()) if self.constructors else []
    
    def get_builder_signatures(self) -> List[str]:
        return list(self.builders.keys()) if self.builders else []
    
    def get_all_related_types(self) -> List[str]:
        related = []
        if self.super_class_name:
            related.append(self.super_class_name)
        related.extend(self.sub_class_names)
        related.extend(self.interfaces)
        related.extend(self.sub_interface_names)
        related.extend(self.implemented_class_names)
        return list(set(related))
    
    def get_summary(self) -> str:
        lines = [
            f"Type: {self.type_name}",
            f"Classification: {self.class_type}"
        ]
        if self.super_class_name:
            lines.append(f"Superclass: {self.super_class_name}")
        if self.sub_class_names:
            lines.append(f"Subclasses: {', '.join(self.sub_class_names)}")
        if self.interfaces:
            lines.append(f"Implements: {', '.join(self.interfaces)}")
        if self.implemented_class_names:
            lines.append(f"Implemented by: {', '.join(self.implemented_class_names)}")
        if self.constructors:
            lines.append(f"Constructors: {len(self.constructors)}")
            for sig in self.constructors.keys():
                lines.append(f"  - {sig}")
        if self.builders:
            lines.append(f"Builder methods: {len(self.builders)}")
            for sig in self.builders.keys():
                lines.append(f"  - {sig}")
        if self.fields:
            lines.append(f"Fields: {len(self.fields)}")
        return '\n'.join(lines)
    
    def to_dict(self) -> dict:
        return self.data
    
    def __repr__(self):
        return f"TypeInfo({self.type_name}, {self.class_type})"


class TypeParseServiceWrapper:
    """Python wrapper for Java TypeParseService via CLI"""
    
    def __init__(self, cli_jar: Optional[str] = None, classpath: Optional[str] = None):
        """
        Args:
            cli_jar: Path to javautils-cli fat JAR (auto-detected if not provided)
            classpath: Java classpath for analyzing target classes
        """
        if cli_jar is None:
            default_jar = os.path.join(JAVA_UTILS_PATH, 'target', 'javautils-cli.jar')
            if os.path.exists(default_jar):
                cli_jar = default_jar
            else:
                raise RuntimeError(f"javautils-cli.jar not found at {default_jar}. Build with: mvn package")
        
        if not os.path.exists(cli_jar):
            raise RuntimeError(f"javautils-cli.jar not found at {cli_jar}")
        
        self.cli_jar = cli_jar
        raw_cp = classpath or CLASS_PATH
        # Normalize classpath: support comma-separated entries by converting to OS path separator
        # Also deduplicate and strip whitespace
        parts = []
        for token in raw_cp.replace(',', os.pathsep).split(os.pathsep):
            # Remove all whitespace inside tokens to guard against accidental newlines in config
            token = re.sub(r"\s+", "", token)
            if not token:
                continue
            # Filter out non-existent entries to avoid Soot failing on invalid classpath segments
            if not os.path.exists(token):
                continue
            if token not in parts:
                parts.append(token)
        self.classpath = os.pathsep.join(parts)
    
    def parse_type_info(self, type_signature: str) -> Optional[TypeInfo]:
        """Parse type information for a single type via CLI"""
        try:
            cmd = [
                'java',
                '-cp', self.cli_jar,
                'javaUtils.TypeParserCLI',
                type_signature,
                self.classpath
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"Error: {result.stderr}")
                return None
            
            json_data = json.loads(result.stdout.strip())
            return TypeInfo(json_data)
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            return None
        except subprocess.TimeoutExpired:
            print(f"Timeout parsing: {type_signature}")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def parse_multiple_types(self, type_signatures: List[str]) -> Dict[str, TypeInfo]:
        result = {}
        for type_sig in type_signatures:
            type_info = self.parse_type_info(type_sig)
            if type_info:
                result[type_sig] = type_info
        return result
    
    def get_constructors(self, type_signature: str) -> List[str]:
        type_info = self.parse_type_info(type_signature)
        return type_info.get_constructor_signatures() if type_info else []
    
    def get_inheritance_hierarchy(self, type_signature: str) -> Dict:
        type_info = self.parse_type_info(type_signature)
        if type_info:
            return {
                'superclass': type_info.super_class_name,
                'subclasses': type_info.sub_class_names,
                'interfaces': type_info.interfaces,
                'sub_interfaces': type_info.sub_interface_names,
                'implementers': type_info.implemented_class_names
            }
        return {}
    
    def get_all_implementations(self, type_signature: str) -> List[str]:
        type_info = self.parse_type_info(type_signature)
        if type_info:
            if type_info.is_interface():
                return type_info.implemented_class_names
            elif type_info.is_abstract():
                return type_info.sub_class_names
        return []


if __name__ == "__main__":
    service = TypeParseServiceWrapper()
    type_info = service.parse_type_info("java.util.ArrayList")
    if type_info:
        print(type_info.get_summary())
