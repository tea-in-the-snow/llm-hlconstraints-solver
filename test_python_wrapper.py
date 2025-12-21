"""
Test Python wrapper with jfreechart classes.
Tests constructor signatures and inheritance polymorphism relationships.
"""

import sys
import os

# Add javaUtils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'javaUtils'))

from type_parse_wrapper import TypeParseServiceWrapper


def test_jfreechart_classes():
    """Test parsing various jfreechart classes"""
    
    # jfreechart JAR path
    jfreechart_classpath = "/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar"
    
    if not os.path.exists(jfreechart_classpath):
        print(f"ERROR: jfreechart JAR not found at {jfreechart_classpath}")
        return False
    
    try:
        # Initialize service with jfreechart classpath
        service = TypeParseServiceWrapper(classpath=jfreechart_classpath)
        
        print("=" * 80)
        print("Testing JFreeChart Classes")
        print("=" * 80)
        
        # Test 1: JFreeChart main class
        print("\n[Test 1] Parsing JFreeChart class")
        print("-" * 80)
        jfreechart_info = service.parse_type_info("org.jfree.chart.JFreeChart")
        
        if jfreechart_info:
            print(f"✓ Successfully parsed JFreeChart")
            print(jfreechart_info.get_summary())
            
            # Print all constructors
            print("\n  All constructors:")
            for ctor in jfreechart_info.get_constructor_signatures():
                print(f"    - {ctor}")
            
            # Print inheritance info
            print(f"\n  Superclass: {jfreechart_info.super_class_name}")
            print(f"  Interfaces: {', '.join(jfreechart_info.interfaces) if jfreechart_info.interfaces else 'None'}")
        else:
            print("✗ Failed to parse JFreeChart")
            return False
        
        # Test 2: XYPlot class
        print("\n[Test 2] Parsing XYPlot class")
        print("-" * 80)
        xyplot_info = service.parse_type_info("org.jfree.chart.plot.XYPlot")
        
        if xyplot_info:
            print(f"✓ Successfully parsed XYPlot")
            print(xyplot_info.get_summary())
            
            # Print all constructors
            print("\n  All constructors:")
            for ctor in xyplot_info.get_constructor_signatures():
                print(f"    - {ctor}")
            
            # Print inheritance info
            print(f"\n  Superclass: {xyplot_info.super_class_name}")
            print(f"  Interfaces: {', '.join(xyplot_info.interfaces) if xyplot_info.interfaces else 'None'}")
        else:
            print("✗ Failed to parse XYPlot")
            return False
        
        # Test 3: CategoryPlot class
        print("\n[Test 3] Parsing CategoryPlot class")
        print("-" * 80)
        catplot_info = service.parse_type_info("org.jfree.chart.plot.CategoryPlot")
        
        if catplot_info:
            print(f"✓ Successfully parsed CategoryPlot")
            print(catplot_info.get_summary())
            
            # Print all constructors
            print("\n  All constructors:")
            for ctor in catplot_info.get_constructor_signatures():
                print(f"    - {ctor}")
        else:
            print("✗ Failed to parse CategoryPlot")
            return False
        
        # Test 4: Inheritance hierarchy
        print("\n[Test 4] Inheritance hierarchy analysis")
        print("-" * 80)
        
        xyplot_hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.XYPlot")
        print(f"XYPlot hierarchy:")
        print(f"  Superclass: {xyplot_hierarchy.get('superclass')}")
        print(f"  Interfaces implemented: {', '.join(xyplot_hierarchy.get('interfaces', []))}")
        print(f"  Subclasses: {', '.join(xyplot_hierarchy.get('subclasses', [])) or 'None'}")
        
        catplot_hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.CategoryPlot")
        print(f"\nCategoryPlot hierarchy:")
        print(f"  Superclass: {catplot_hierarchy.get('superclass')}")
        print(f"  Interfaces implemented: {', '.join(catplot_hierarchy.get('interfaces', []))}")
        print(f"  Subclasses: {', '.join(catplot_hierarchy.get('subclasses', [])) or 'None'}")
        
        # Test 5: Batch parsing
        print("\n[Test 5] Batch parsing multiple types")
        print("-" * 80)
        
        types_to_parse = [
            "org.jfree.chart.JFreeChart",
            "org.jfree.chart.plot.XYPlot",
            "org.jfree.chart.plot.CategoryPlot",
            "org.jfree.chart.ChartPanel",
            "org.jfree.chart.axis.ValueAxis"
        ]
        
        results = service.parse_multiple_types(types_to_parse)
        print(f"Successfully parsed {len(results)} out of {len(types_to_parse)} types:")
        for type_sig, info in results.items():
            ctor_count = len(info.get_constructor_signatures())
            print(f"  ✓ {type_sig.split('.')[-1]}: {ctor_count} constructors")
        
        # Test 6: Plot interface implementations
        print("\n[Test 6] Plot interface implementations")
        print("-" * 80)
        
        plot_interface = "org.jfree.chart.plot.Plot"
        implementations = service.get_all_implementations(plot_interface)
        if implementations:
            print(f"Plot interface is implemented by {len(implementations)} classes:")
            for impl in sorted(implementations)[:10]:  # Show first 10
                print(f"  - {impl}")
            if len(implementations) > 10:
                print(f"  ... and {len(implementations) - 10} more")
        else:
            print("Could not determine implementations for Plot interface")
        
        print("\n" + "=" * 80)
        print("All tests passed! ✓")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_jfreechart_interfaces():
    """Test parsing interface types in jfreechart"""
    
    jfreechart_classpath = "/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar"
    
    if not os.path.exists(jfreechart_classpath):
        print(f"ERROR: jfreechart JAR not found at {jfreechart_classpath}")
        return False
    
    try:
        service = TypeParseServiceWrapper(classpath=jfreechart_classpath)
        
        print("\n" + "=" * 80)
        print("Testing JFreeChart Interface Types")
        print("=" * 80)
        
        # Test 1: Plot interface
        print("\n[Interface Test 1] Parsing Plot interface")
        print("-" * 80)
        plot_info = service.parse_type_info("org.jfree.chart.plot.Plot")
        
        if not plot_info:
            print("✗ Failed to parse Plot interface")
            return False
        
        if not plot_info.is_interface():
            print(f"✗ Plot should be interface, got: {plot_info.class_type}")
            return False
        
        print(f"✓ Successfully parsed Plot as interface")
        print(f"\n  Type Name: {plot_info.type_name}")
        print(f"  Classification: {plot_info.class_type}")
        
        # Check for implementing classes
        implementers = plot_info.implemented_class_names
        print(f"\n  Implementing Classes ({len(implementers)}):")
        for impl in sorted(implementers)[:8]:
            print(f"    - {impl}")
        if len(implementers) > 8:
            print(f"    ... and {len(implementers) - 8} more")
        
        # Test 2: ValueAxisPlot interface
        print("\n[Interface Test 2] Parsing ValueAxisPlot interface")
        print("-" * 80)
        vap_info = service.parse_type_info("org.jfree.chart.plot.ValueAxisPlot")
        
        if not vap_info:
            print("✗ Failed to parse ValueAxisPlot interface")
            return False
        
        if not vap_info.is_interface():
            print(f"✗ ValueAxisPlot should be interface, got: {vap_info.class_type}")
            return False
        
        print(f"✓ Successfully parsed ValueAxisPlot as interface")
        print(f"\n  Type Name: {vap_info.type_name}")
        print(f"  Classification: {vap_info.class_type}")
        
        vap_implementers = vap_info.implemented_class_names
        print(f"\n  Implementing Classes ({len(vap_implementers)}):")
        for impl in sorted(vap_implementers)[:5]:
            print(f"    - {impl}")
        if len(vap_implementers) > 5:
            print(f"    ... and {len(vap_implementers) - 5} more")
        
        # Test 3: Zoomable interface
        print("\n[Interface Test 3] Parsing Zoomable interface")
        print("-" * 80)
        zoom_info = service.parse_type_info("org.jfree.chart.plot.Zoomable")
        
        if not zoom_info:
            print("✗ Failed to parse Zoomable interface")
            return False
        
        if not zoom_info.is_interface():
            print(f"✗ Zoomable should be interface, got: {zoom_info.class_type}")
            return False
        
        print(f"✓ Successfully parsed Zoomable as interface")
        print(f"\n  Type Name: {zoom_info.type_name}")
        print(f"  Classification: {zoom_info.class_type}")
        print(f"  Methods: {len(zoom_info.methods)}")
        if zoom_info.methods:
            for method in zoom_info.methods[:3]:
                print(f"    - {method}")
        
        zoom_implementers = zoom_info.implemented_class_names
        print(f"\n  Implementing Classes ({len(zoom_implementers)}):")
        for impl in sorted(zoom_implementers)[:5]:
            print(f"    - {impl}")
        
        # Test 4: Interface hierarchy
        print("\n[Interface Test 4] Interface hierarchy analysis")
        print("-" * 80)
        
        plot_hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.Plot")
        print(f"Plot interface hierarchy:")
        print(f"  Type: Interface")
        print(f"  Sub-interfaces: {len(plot_hierarchy.get('sub_interfaces', []))} ")
        if plot_hierarchy.get('sub_interfaces'):
            for sub in plot_hierarchy.get('sub_interfaces', [])[:5]:
                print(f"    - {sub}")
        print(f"  Implementers: {len(plot_hierarchy.get('implementers', []))} classes")
        
        # Test 5: Batch parse interfaces
        print("\n[Interface Test 5] Batch parsing multiple interfaces")
        print("-" * 80)
        
        interfaces_to_parse = [
            "org.jfree.chart.plot.Plot",
            "org.jfree.chart.plot.ValueAxisPlot",
            "org.jfree.chart.plot.Zoomable",
            "org.jfree.chart.plot.Pannable",
            "org.jfree.chart.event.RendererChangeListener"
        ]
        
        results = service.parse_multiple_types(interfaces_to_parse)
        print(f"Successfully parsed {len(results)} out of {len(interfaces_to_parse)} interfaces:")
        
        for type_sig, info in results.items():
            short_name = type_sig.split('.')[-1]
            if info.is_interface():
                impl_count = len(info.implemented_class_names)
                print(f"  ✓ {short_name}: interface with {impl_count} implementers")
            else:
                print(f"  ⚠ {short_name}: parsed as {info.class_type}, not interface")
        
        # Test 6: Interface implementation verification
        print("\n[Interface Test 6] Verify interface implementation")
        print("-" * 80)
        
        # Parse XYPlot and verify it implements expected interfaces
        xyplot_info = service.parse_type_info("org.jfree.chart.plot.XYPlot")
        if xyplot_info:
            expected_interfaces = [
                "org.jfree.chart.plot.ValueAxisPlot",
                "org.jfree.chart.plot.Zoomable"
            ]
            
            print(f"XYPlot should implement:")
            for expected in expected_interfaces:
                if expected in xyplot_info.interfaces:
                    print(f"  ✓ {expected.split('.')[-1]}")
                else:
                    print(f"  ✗ {expected.split('.')[-1]} (NOT FOUND)")
            
            print(f"\nAll XYPlot interfaces:")
            for iface in xyplot_info.interfaces:
                print(f"  - {iface}")
        
        print("\n" + "=" * 80)
        print("Interface analysis tests completed! ✓")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n✗ Interface test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run both test suites
    success1 = test_jfreechart_classes()
    success2 = test_jfreechart_interfaces()
    
    if success1 and success2:
        print("\n✓ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
