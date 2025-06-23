# AAA Issue Refactor Tool - Quick Start Guide

*A step-by-step guide for students to use the tool through Phase 3 and perform code review*

---

## **At-a-glance**

| **What you need** | **macOS / Linux** | **Windows 11 (WSL2 Ubuntu 24.04)** |
| --- | --- | --- |
| **WSL2 Setup** | N/A | wsl --install -d Ubuntu-24.04 |
| Python ≥ 3.12 + uv | brew install python@3.13 → brew install uv | apt install python3-dev → curl uv install |
| Java + Build tools | brew install openjdk@21 maven | apt install openjdk-21-jdk maven |
| Git & development tools | brew install git | apt install git build-essential |
| **VS Code + WSL Extension** | Download VS Code | Download VS Code + WSL extension |
| OpenAI API key | **Provided by instructor – set in .env file** | same |
| AAA Issue Refactor Tool | git clone → uv sync → configure .env | same (use WSL2 terminal) |

---

## **1. System requirements**

- **OS**
    - macOS 12+ or recent Linux distro (Ubuntu 24.04)
    - Windows 11 64-bit with **WSL2 Ubuntu 24.04** (required for Windows users)
- **Disk** ≥ 15 GB free for dependencies and WSL2 (if using Windows)
- **Memory** 8 GB+ recommended (WSL2 uses ~2GB additional RAM)
- **Java project** with Maven/Gradle build system
- **Git repository** initialized in your Java project

> **🚨 Important for Windows users:** Native Windows installation is **not supported**. You **must** use WSL2 Ubuntu 24.04 for consistent behavior with macOS/Linux environments.

---

## **2. Windows WSL2 Setup (Windows Users Only)**

### **Why WSL2?**

Windows Subsystem for Linux 2 (WSL2) provides a complete Linux environment on Windows, ensuring consistent behavior with macOS/Linux development workflows. This is **required** for Windows users.

### **Step 1: Enable WSL2**

Open **PowerShell as Administrator** and run:

```powershell
# Enable WSL and Virtual Machine Platform
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# Restart your computer
shutdown /r /t 0
```

After restart, open **PowerShell as Administrator** again:

```powershell
# Set WSL2 as default version
wsl --set-default-version 2

# Install Ubuntu 24.04
wsl --install -d Ubuntu-24.04
```

### **Step 2: Initial Ubuntu Setup**

When Ubuntu starts for the first time:

1. **Create a username** (use lowercase, no spaces)
2. **Create a password** (you'll need this for sudo commands)
3. **Update the system**:

```bash
sudo apt update && sudo apt upgrade -y
```

### **Step 3: Install Development Tools in WSL2**

Run these commands **inside your WSL2 Ubuntu terminal**:

```bash
# Essential development packages
sudo apt install -y curl wget git build-essential python3-dev python3-pip

# Install Java 21
sudo apt install -y openjdk-21-jdk

# Install Maven
sudo apt install -y maven

# Install Gradle
wget https://services.gradle.org/distributions/gradle-8.5-bin.zip
sudo mkdir /opt/gradle
sudo unzip -d /opt/gradle gradle-8.5-bin.zip
echo 'export PATH=$PATH:/opt/gradle/gradle-8.5/bin' >> ~/.bashrc
source ~/.bashrc

# Install Python uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### **Step 4: Set Environment Variables**

Add these to your `~/.bashrc` file:

```bash
# Edit bashrc
nano ~/.bashrc

# Add these lines at the end:
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH=$PATH:$JAVA_HOME/bin
export PATH=$PATH:/opt/gradle/gradle-8.5/bin

# Save and reload
source ~/.bashrc
```

### **Step 5: VS Code Integration**

**Install VS Code Extensions:**

1. **On Windows**: Install VS Code from https://code.visualstudio.com/
2. **Install WSL Extension**: In VS Code, install "WSL" extension by Microsoft
3. **Connect to WSL**: Press `Ctrl+Shift+P` → Type "WSL: Connect to WSL"

**Working with Projects:**

```bash
# In WSL2 terminal, navigate to your project
cd /path/to/your/java/project

# Open in VS Code (this opens VS Code connected to WSL2)
code .
```

**VS Code will automatically:**
- Use WSL2's Java, Maven, and other tools
- Provide integrated terminal access to WSL2
- Handle file system mapping between Windows and Linux

### **Step 6: Verify WSL2 Setup**

Run this verification script in your **WSL2 terminal**:

```bash
# Verify all tools are installed correctly
echo "=== WSL2 Environment Check ==="
lsb_release -a                    # Ubuntu version
java -version                     # Java 21
mvn -version                      # Maven
gradle -version                   # Gradle  
python3 --version                 # Python 3
uv --version                      # uv package manager
git --version                     # Git
echo "JAVA_HOME: $JAVA_HOME"      # Java home path
```

**Expected output:**
- Ubuntu 24.04.x LTS
- OpenJDK 21.x
- Maven 3.9.x
- Gradle 8.5
- Python 3.12.x
- uv 0.x.x
- Git 2.x.x
- JAVA_HOME should point to Java 21

### **WSL2 Best Practices**

| **Practice** | **Why** |
| --- | --- |
| **Keep projects in WSL2 filesystem** | Better performance (`/home/username/projects`) |
| **Use WSL2 terminal for all commands** | Avoid Windows/Linux path conflicts |
| **Install tools in WSL2, not Windows** | Consistent environment |
| **Use VS Code with WSL extension** | Seamless development experience |

### **Common WSL2 Issues**

| **Problem** | **Solution** |
| --- | --- |
| **WSL2 not starting** | `wsl --shutdown` then `wsl` |
| **VS Code can't connect** | Restart VS Code, ensure WSL extension installed |
| **Java not found** | Check `JAVA_HOME` and `PATH` in `~/.bashrc` |
| **Permission errors** | Use `sudo` for system operations |

---

## **3. Install Python and uv (macOS/Linux only)**

> **Windows users:** Skip this section - you installed everything in WSL2 already!

### **macOS / Linux**

```bash
brew install python@3.13              # Python 3.13+ required
curl -LsSf https://astral.sh/uv/install.sh | sh    # install uv package manager
```

**Verify:**
```bash
python --version    # should report 3.13+
uv --version       # should report latest uv version
```

---

## **4. Install Java and build tools (macOS/Linux only)**

> **Windows users:** Skip this section - you installed everything in WSL2 already!

### **macOS / Linux**

```bash
brew install openjdk@21     # Java 21 LTS
brew install maven          # Maven build tool
```

**Verify:**
```bash
java -version   # should report 21.x
mvn -v         # should report Maven version
```

---

## **5. Git setup**

### **Install Git**

**macOS / Linux:**
```bash
brew install git
```

**Windows WSL2:**
```bash
# Git is already installed in WSL2 Ubuntu, but configure it:
git config --global user.name "Your Full Name"
git config --global user.email "you@stevens.edu"
```

### **Configure Git Identity**

Set up your Git identity (**all platforms**):
```bash
git config --global user.name "Your Full Name"
git config --global user.email "you@stevens.edu"
```

### **Prepare Your Java Project**

Make sure your Java project is a git repository:

**macOS/Linux:**
```bash
cd /path/to/your/java/project
git init
git add .
git commit -m "Initial commit"
```

**Windows WSL2:**
```bash
# Work in WSL2 filesystem for better performance
cd /home/username/projects/your-java-project
git init
git add .
git commit -m "Initial commit"
```

---

## **6. Install AAA Issue Refactor Tool**

### **Clone and Setup**

**All platforms (use terminal/WSL2 for Windows):**

```bash
# Clone the tool repository
git clone <repository-url>
cd AAA-Issue-Refactor

# Install dependencies
uv sync

# Create environment file
cp .env.example .env
```

### **Configure OpenAI API Key**

Your instructor will provide the OpenAI API key. **Do not generate your own** - use the provided course key.

**Edit the .env file (all platforms):**

```bash
# Edit .env file
nano .env

# Add this line with your provided key:
OPENAI_API_KEY=sk-your-actual-api-key-here
```

**Verify configuration:**
```bash
# Check that the key is properly set
cat .env | grep OPENAI_API_KEY
```

---

## **7. Smoke-test checklist**

Run these commands to verify everything is working (**use WSL2 terminal for Windows**):

```bash
# Environment verification
python3 --version             # ≥ 3.12 (Ubuntu) / 3.13 (macOS)
uv --version                  # latest uv
java -version                 # 21.x
mvn -version                  # Maven 3.9.x
git --version                 # Git version

# Tool and configuration verification
cd AAA-Issue-Refactor
cat .env | grep OPENAI_API_KEY    # Should show your key (starts with sk-)
uv run aif --version              # Should show tool version

# WSL2 specific (Windows users only)
lsb_release -a               # Should show Ubuntu 24.04.x LTS
echo $JAVA_HOME              # Should point to Java 21
```

**Expected output for all platforms:**
- Python 3.12+ or 3.13+
- uv package manager installed
- Java 21.x (OpenJDK)
- Maven 3.9.x
- Git 2.x.x
- OpenAI API key visible in .env file
- AAA Issue Refactor tool version

---

## **8. Input Data Requirements**

You need two types of input files (provided by instructor):

| **File Type** | **Format** | **Contents** |
| --- | --- | --- |
| **AAA Results CSV** | `<project_name> AAAResults.csv` | Test cases with AAA violations |
| **JSON Context Files** | `<project_name>_<test_class>_<test_method>.json` | Test context per method |

**Required CSV columns:** project_name, test_class_name, test_method_name, issue_type

---

## **Phase-by-Phase Workflow**

### **Phase 1: Discovery & Validation**

**Purpose:** Validate your test cases and prepare them for refactoring.

```bash
cd AAA-Issue-Refactor

uv run aif --project /path/to/your/java/project \
          --data /path/to/your/data/folder \
          --output /path/to/output/folder \
          --discovery-only \
          --no-auto-update
```

| **What it does** | **Output** |
| --- | --- |
| ✅ Checks if test files exist | `project_AAA_Refactor_Cases.csv` |
| ✅ Validates test compilation | Console: "Runnable test cases: X/Y" |
| ✅ Verifies test execution |  |

---

### **Phase 2: Refactoring with AAA Strategy**

**Purpose:** Generate refactored code using LLM.

```bash
uv run aif --project /path/to/your/java/project \
          --data /path/to/your/data/folder \
          --output /path/to/output/folder \
          --refactor-only --rftype aaa \
          --input-file /path/to/output/project_AAA_Refactor_Cases.csv \
          --no-auto-update
```

| **What it does** | **Output** |
| --- | --- |
| 🤖 Uses OpenAI o4-mini to refactor | `project_refactored_result.csv` |
| 🔄 Iterative improvement (≤5 rounds) | `project-usage.csv` |
| 💰 Tracks costs (~$0.01-0.03/test) | Console: Success rate & costs |

---

### **Phase 3: Execution Testing**

**Purpose:** Integrate refactored code and test functionality.

```bash
uv run aif --project /path/to/your/java/project \
          --data /path/to/your/data/folder \
          --output /path/to/output/folder \
          --execution-test-only \
          --no-auto-update
```

| **What it does** | **Result** |
| --- | --- |
| 🧹 Auto-cleans existing refactored code | Original files restored |
| 🔗 Integrates refactored methods | Temporary modifications |
| ▶️ Executes each refactored test | Pass/fail results recorded |
| 🔄 Restores original files | Clean project state |

---

## **Code Review Workflow**

### **Step 1: Generate Review-Friendly Code**

**Purpose:** Create code that's easy to review and compare.

```bash
uv run aif --project /path/to/your/java/project \
          --data /path/to/your/data/folder \
          --output /path/to/output/folder \
          --show-refactored-only \
          --keep-rf-in-project \
          --no-auto-update
```

| **What it does** | **Benefit** |
| --- | --- |
| 📚 Adds refactored methods to test classes | Side-by-side comparison |
| 🔄 **Preserves original methods unchanged** | Non-destructive review |
| 🏷️ Auto-renames methods to avoid conflicts | No compilation errors |
| 📝 Adds visual separators and comments | Clear organization |

---

### **Step 2: Manual Code Review**

Navigate to your Java project and review:

```bash
cd /path/to/your/java/project
git status                    # Check modified files
git diff TestClass.java       # Review specific changes
```

**Review checklist:**

| **Category** | **Look for** |
| --- | --- |
| **Code Quality** | ✅ Clear AAA structure<br>✅ Descriptive method names<br>✅ Proper assertions<br>✅ No duplication |
| **Correctness** | ✅ Logic matches original intent<br>✅ Edge cases covered<br>✅ Appropriate test data |
| **Style** | ✅ Consistent formatting<br>✅ Clear variable names<br>✅ Proper comments |

**Example of generated code**:
```java
// Original method (preserved unchanged)
@Test
public void testOriginalMethod() { 
    /* original code remains here */ 
}

/*
 * ================================================================================
 * REFACTORED METHODS FOR: testOriginalMethod
 * Original Issue Type: Multiple AAA
 * Generated by AAA Issue Refactor Tool
 * ================================================================================
 */

/*
 * --------------------------------------------------------------------------------
 * STRATEGY: AAA 
 * --------------------------------------------------------------------------------
 */
@Test
public void testOriginalMethodWithValidInput() {
    // Arrange
    String input = "valid";
    
    // Act
    boolean result = someMethod(input);
    
    // Assert
    assertTrue(result);
}

@Test
public void testOriginalMethodWithInvalidInput() {
    // Arrange
    String input = null;
    
    // Act
    boolean result = someMethod(input);
    
    // Assert
    assertFalse(result);
}
```

---

### **Step 3: Clean Up After Review**

**Purpose:** Remove refactored code before running official tests.

```bash
cd AAA-Issue-Refactor

uv run aif --project /path/to/your/java/project \
          --data /path/to/your/data/folder \
          --output /path/to/output/folder \
          --clean-refactored-only \
          --no-auto-update
```

| **What it does** | **Result** |
| --- | --- |
| 🧹 Uses git to restore Java files | Original state restored |
| 📊 Reports cleaned files | Console: "X files restored" |
| ✅ Prevents contamination | Clean for future tests |

---

## **Understanding Costs**

### **Cost Analysis Files**

| **File** | **Contents** |
| --- | --- |
| `<project_name>-usage.csv` | Detailed per-test-case costs |
| Console output | Real-time summary statistics |

### **Typical Performance (10 test cases)**

| **Metric** | **Expected Range** |
| --- | --- |
| **Cost per test case** | $0.01 - $0.03 |
| **Processing time** | 15-45 seconds per test |
| **Success rate** | 80-100% |
| **LLM iterations** | 1-2 rounds |

### **Cost Management Tips**

| **Strategy** | **Benefit** |
| --- | --- |
| ✅ Start with 5-10 test cases | Low initial cost |
| ✅ Use AAA strategy first | Cheapest option |
| ✅ Monitor console output | Real-time tracking |
| ⚠️ Set cost limits | Prevent overruns |

---

## **Troubleshooting**

### **Common Issues**

| **Problem** | **Solution** |
| --- | --- |
| **❌ OpenAI API failures** | `cat .env \| grep OPENAI_API_KEY` - verify key in .env file |
| **❌ Java compilation errors** | `mvn clean compile test-compile` - test manually |
| **❌ Git repository not found** | `git init && git add . && git commit -m "init"` |
| **❌ No refactoring results** | Complete Phase 2 first, check output directory |

### **Debugging Commands**

```bash
# Verify environment
python3 --version && uv --version && java -version

# Check OpenAI key configuration
cd AAA-Issue-Refactor
cat .env | grep OPENAI_API_KEY

# Test Java project
cd /path/to/java/project
mvn clean compile test-compile

# Check tool installation
cd AAA-Issue-Refactor
uv run aif --version

# Debug mode (verbose output)
uv run aif [normal-args] --debug
```

### **Getting Help**

- ✅ Check console output for error details
- ✅ Use `--debug` flag for verbose logging  
- ✅ Verify all prerequisites in smoke-test
- ✅ Confirm input data format and completeness

---

## **Next Steps**

After completing Phase 3 and review:

| **Advanced Topic** | **Purpose** |
| --- | --- |
| **Multiple Strategies** | Try DSL and TestSmell for comparison |
| **PIT Testing** | Run Phase 4 for mutation testing |
| **Batch Processing** | Scale up to larger test sets |
| **Statistical Analysis** | Use CSV outputs for research |

---

## **Quick Command Reference**

```bash
# Complete workflow for students
cd AAA-Issue-Refactor

# 1. Discovery
uv run aif --project /path/to/java --data /path/to/data --output /path/to/output --discovery-only --no-auto-update

# 2. Refactoring  
uv run aif --project /path/to/java --data /path/to/data --output /path/to/output --refactor-only --rftype aaa --input-file /path/to/output/project_AAA_Refactor_Cases.csv --no-auto-update

# 3. Testing
uv run aif --project /path/to/java --data /path/to/data --output /path/to/output --execution-test-only --no-auto-update

# 4. Review (optional)
uv run aif --project /path/to/java --data /path/to/data --output /path/to/output --show-refactored-only --keep-rf-in-project --no-auto-update

# 5. Cleanup (after review)
uv run aif --project /path/to/java --data /path/to/data --output /path/to/output --clean-refactored-only --no-auto-update
```

---

## **Success Checklist**

You've successfully completed the workflow when:

| **Milestone** | **Status** |
| --- | --- |
| ✅ All phases complete without errors | [ ] |
| 📊 CSV files generated with results | [ ] |
| 💰 Cost analysis shows reasonable expenses | [ ] |
| 🧪 Refactored tests pass execution | [ ] |
| 📝 Code review reveals quality improvements | [ ] |
| 🧹 Original files cleanly restored | [ ] |

**Happy refactoring! 🎉** 