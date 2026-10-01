-- Fault injection per connector operation (rotation and account disable included).
ALTER TABLE sandbox_faults DROP CONSTRAINT sandbox_faults_operation_check;
ALTER TABLE sandbox_faults ADD CONSTRAINT sandbox_faults_operation_check
 CHECK (operation IN ('remove_relationship','add_relationship','rotate_credential','disable_account'));
