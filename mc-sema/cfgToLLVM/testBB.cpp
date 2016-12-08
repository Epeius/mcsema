#include "toLLVM.h"
#include "raiseX86.h"
#include "X86.h"
#include "x86Instrs.h"
#include "x86Helpers.h"
#include "win32cb.h"
#include <set>
#include <map>
#include <iostream>

#include <llvm/Object/COFF.h>
#include <llvm/IR/Constants.h>
#include <llvm/ADT/StringSwitch.h>
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/DebugInfo.h"
#include "llvm/IR/Module.h"
#include "llvm/Bitcode/ReaderWriter.h"
#include "llvm/LinkAllPasses.h"
#include "llvm/PassManager.h"
#include "llvm/Transforms/IPO/PassManagerBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Transforms/Utils/BasicBlockUtils.h"
#include "win32_Intrinsics.h"

using namespace std;
using namespace llvm;

struct testBB : public BasicBlockPass {
  static char ID;
  testBB() : BasicBlockPass(ID) {}

  bool runOnBasicBlock(BasicBlock &B) override {
    errs() << "Test Basic Block: ";
    errs().write_escaped(B.getName()) << '\n';
    return false;
  }
}; // end of struct testBB

char testBB::ID = 0;
static RegisterPass<testBB> X("testBB", "testBB Pass",
                             false /* Only looks at CFG */,
                             false /* Analysis Pass */);


void TestBB(const PassManagerBuilder &Builder, PassManagerBase &PM) {
    //register the pass
    PM.add(new testBB());
    return;
}
