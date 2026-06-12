#!/usr/bin/env python3
"""
测试 UI 树保存功能
"""
import sys
from pathlib import Path

# 添加 src 目录
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

print("=" * 60)
print("测试 UI 树保存功能")
print("=" * 60)

try:
    # 1. 测试导入
    print("\n[1] 测试导入...")
    from common.config import settings
    from common.logger import setup_logger, logger
    
    # 2. 开启 debug 模式
    print("\n[2] 开启 debug 模式...")
    settings.DEBUG = True
    setup_logger(debug=True)
    
    print(f"✅ Debug 模式已开启")
    print(f"   日志文件: {settings.LOG_FILE_DEBUG}")
    print(f"   截图目录: {settings.REPORT_SCREENSHOT_SAVE_DIR}")
    
    # 3. 测试目录
    print("\n[3] 检查输出目录...")
    screenshots_dir = Path(settings.REPORT_SCREENSHOT_SAVE_DIR)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ 截图目录: {screenshots_dir.absolute()}")
    
    print("\n" + "=" * 60)
    print("✅ 测试准备完成！")
    print("\n现在你可以运行你的自动化脚本，")
    print("UI 树会自动保存到 ./output/reports/screenshots/ 目录")
    print("\n你会看到类似这样的日志:")
    print("   ✅ 原始 UI 树已保存: ...")
    print("   ✅ 解析后的 UI 树已保存: ...")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
