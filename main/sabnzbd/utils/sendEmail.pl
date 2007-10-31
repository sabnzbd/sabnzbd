#!/usr/bin/perl -w
##############################################################################
## sendEmail
## Written by: Brandon Zehm <caspian@dotconf.net>
## 
## License:
##  sendEmail (hereafter referred to as "program") is free software;
##  you can redistribute it and/or modify it under the terms of the GNU General
##  Public License as published by the Free Software Foundation; either version
##  2 of the License, or (at your option) any later version.
##  When redistributing modified versions of this source code it is recommended
##  that that this disclaimer and the above coder's names are included in the
##  modified code.
##  
## Disclaimer:
##  This program is provided with no warranty of any kind, either expressed or
##  implied.  It is the responsibility of the user (you) to fully research and
##  comprehend the usage of this program.  As with any tool, it can be misused,
##  either intentionally (you're a vandal) or unintentionally (you're a moron).
##  THE AUTHOR(S) IS(ARE) NOT RESPONSIBLE FOR ANYTHING YOU DO WITH THIS PROGRAM
##  or anything that happens because of your use (or misuse) of this program,
##  including but not limited to anything you, your lawyers, or anyone else
##  can dream up.  And now, a relevant quote directly from the GPL:
##  
## NO WARRANTY
##  
##  11. BECAUSE THE PROGRAM IS LICENSED FREE OF CHARGE, THERE IS NO WARRANTY
##  FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW.  EXCEPT WHEN
##  OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES
##  PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED
##  OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
##  MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.  THE ENTIRE RISK AS
##  TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU.  SHOULD THE
##  PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING,
##  REPAIR OR CORRECTION.
##    
##############################################################################
use strict;
use IO::Socket;


########################
##  Global Variables  ##
########################

my %conf = (
    ## General
    "programName"          => $0,                                  ## The name of this program
    "version"              => '1.55',                              ## The version of this program
    "authorName"           => 'Brandon Zehm',                      ## Author's Name
    "authorEmail"          => 'caspian@dotconf.net',               ## Author's Email Address
    "timezone"             => '+0000',                             ## We always use +0000 for the time zone
    "hostname"             => 'changeme',                          ## Used in printmsg() for all output (is updated later in the script).
    "debug"                => 0,                                   ## Default debug level
    "error"                => '',                                  ## Error messages will often be stored here
    
    ## Logging
    "stdout"               => 1,
    "logging"              => 0,                                   ## If this is true the printmsg function prints to the log file
    "logFile"              => '',                                  ## If this is specified (form the command line via -l) this file will be used for logging.
    
    ## Network
    "server"               => 'localhost',                         ## Default SMTP server
    "port"                 => 25,                                  ## Default port
    "bindaddr"             => '',                                  ## Default local bind address
    "alarm"                => '',                                  ## Default timeout for connects and reads, this gets set from $opt{'timeout'}
    "tls_client"           => 0,                                   ## If TLS is supported by the client (us)
    "tls_server"           => 0,                                   ## If TLS is supported by the remote SMTP server
    
    ## Email
    "delimiter"            => "----MIME delimiter for sendEmail-"  ## MIME Delimiter
                              . rand(1000000),                     ## Add some randomness to the delimiter
    "Message-ID"           => rand(1000000) . "-sendEmail",        ## Message-ID for email header
    
);


## This hash stores the options passed on the command line via the -o option.
my %opt = (
    ## Addressing
    "reply-to"             => '',                                  ## Reply-To field
    
    ## Message
    "message-file"         => '',                                  ## File to read message body from
    "message-header"       => '',                                  ## Additional email header line(s)
    "message-format"       => 'normal',                            ## If "raw" is specified the message is sent unmodified
    "message-charset"      => 'iso-8859-1',                        ## Message character-set
    
    ## Network
    "timeout"              => 60,                                  ## Default timeout for connects and reads, this is copied to $conf{'alarm'} later.
    "fqdn"                 => 'changeme',                          ## FQDN of this machine, used during SMTP communication (is updated later in the script).
    
    ## eSMTP
    "username"             => '',                                  ## Username used in SMTP Auth
    "password"             => '',                                  ## Password used in SMTP Auth
    "tls"                  => 'auto',                              ## Enable or disable TLS support.  Options: auto, yes, no
    
);

## More variables used later in the program
my $SERVER;
my $CRLF        = "\015\012";
my $subject     = '';
my $header      = '';
my $message     = '';
my $from        = '';
my @to          = ();
my @cc          = ();
my @bcc         = ();
my @attachments = ();
my @attachments_names = ();

## For printing colors to the console
my ${colorRed}    = "\033[31;1m";
my ${colorGreen}  = "\033[32;1m";
my ${colorCyan}   = "\033[36;1m";
my ${colorWhite}  = "\033[37;1m";
my ${colorNormal} = "\033[m";
my ${colorBold}   = "\033[1m";
my ${colorNoBold} = "\033[0m";

## Don't use shell escape codes on Windows systems
if ($^O =~ /win/i) {
    ${colorRed}   = ""; ${colorGreen}  = ""; ${colorCyan} = ""; 
    ${colorWhite} = ""; ${colorNormal} = ""; ${colorBold} = ""; ${colorNoBold} = "";
}

## Load IO::Socket::SSL if it's available
eval    { require IO::Socket::SSL; };
if ($@) { $conf{'tls_client'} = 0; }
else    { $conf{'tls_client'} = 1; }






#############################
##                          ##
##      FUNCTIONS            ##
##                          ##
#############################





###############################################################################################
##  Function: initialize ()
##  
##  Does all the script startup jibberish.
##  
###############################################################################################
sub initialize {

    ## Set STDOUT to flush immediatly after each print  
    $| = 1;
    
    ## Intercept signals
    $SIG{'QUIT'}  = sub { quit("EXITING: Received SIG$_[0]", 1); };
    $SIG{'INT'}   = sub { quit("EXITING: Received SIG$_[0]", 1); };
    $SIG{'KILL'}  = sub { quit("EXITING: Received SIG$_[0]", 1); };
    $SIG{'TERM'}  = sub { quit("EXITING: Received SIG$_[0]", 1); };
  
    ## ALARM and HUP signals are not supported in Win32
    unless ($^O =~ /win/i) {
        $SIG{'HUP'}   = sub { quit("EXITING: Received SIG$_[0]", 1); };
        $SIG{'ALRM'}  = sub { quit("EXITING: Received SIG$_[0]", 1); };
    }
    
    ## Fixup $conf{'programName'}
    $conf{'programName'} =~ s/(.)*[\/,\\]//;
    $0 = $conf{'programName'} . " " . join(" ", @ARGV);
    
    ## Fixup $conf{'hostname'} and $opt{'fqdn'}
    if ($opt{'fqdn'} eq 'changeme') { $opt{'fqdn'} = get_hostname(1); }
    if ($conf{'hostname'} eq 'changeme') { $conf{'hostname'} = $opt{'fqdn'}; $conf{'hostname'} =~ s/\..*//; }
    
    return(1);
}















###############################################################################################
##  Function: processCommandLine ()
##  
##  Processes command line storing important data in global vars (usually %conf)
##  
###############################################################################################
sub processCommandLine {
    
    
    ############################
    ##  Process command line  ##
    ############################
    
    my @ARGS = @ARGV;  ## This is so later we can re-parse the command line args later if we need to
    my $numargv = @ARGS;
    help() unless ($numargv);
    my $counter = 0;
    
    for ($counter = 0; $counter < $numargv; $counter++) {
  
        if ($ARGS[$counter] =~ /^-h$/i) {                    ## Help ##
            help();
        }
        
        elsif ($ARGS[$counter] eq "") {                      ## Ignore null arguments
            ## Do nothing
        }
        
        elsif ($ARGS[$counter] =~ /^--help/) {               ## Topical Help ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                helpTopic($ARGS[$counter]);
            }
            else {
                help();
            }
        }
        
        elsif ($ARGS[$counter] =~ /^-o$/i) {                 ## Options specified with -o ##
            $counter++;
            ## Loop through each option passed after the -o
            while ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                
                if ($ARGS[$counter] !~ /(\S+)=(\S.*)/) {
                    printmsg("WARNING => Name/Value pair [$ARGS[$counter]] is not properly formatted", 0);
                    printmsg("WARNING => Arguments proceeding -o should be in the form of \"name=value\"", 0);
                }
                else {
                    if (exists($opt{$1})) {
                        if ($1 eq 'message-header') {
                            $opt{$1} .= $2 . $CRLF;
                        }
                        else {
                            $opt{$1} = $2;
                        }
                        printmsg("DEBUG => Assigned \$opt{} key/value: $1 => $2", 3);
                    }
                    else {
                        printmsg("WARNING => Name/Value pair [$ARGS[$counter]] will be ignored: unknown key [$1]", 0);
                        printmsg("HINT => Try the --help option to find valid command line arguments", 1);
                    }
                }
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-f$/) {                  ## From ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) { $from = $ARGS[$counter]; }
            else { printmsg("WARNING => The argument after -f was not an email address!", 0); $counter--; }
        }
        
        elsif ($ARGS[$counter] =~ /^-t$/) {                  ## To ##
            $counter++;
            while ($ARGS[$counter] && ($ARGS[$counter] !~ /^-/)) {
                if ($ARGS[$counter] =~ /[;,]/) {
                    push (@to, split(/[;,]/, $ARGS[$counter]));
                }
                else {
                    push (@to,$ARGS[$counter]);
                }
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-cc$/) {                 ## Cc ##
            $counter++;
            while ($ARGS[$counter] && ($ARGS[$counter] !~ /^-/)) {
                if ($ARGS[$counter] =~ /[;,]/) {
                    push (@cc, split(/[;,]/, $ARGS[$counter]));
                }
                else {
                    push (@cc,$ARGS[$counter]);
                }
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-bcc$/) {                ## Bcc ##
            $counter++;
            while ($ARGS[$counter] && ($ARGS[$counter] !~ /^-/)) {
                if ($ARGS[$counter] =~ /[;,]/) {
                    push (@bcc, split(/[;,]/, $ARGS[$counter]));
                }
                else {
                    push (@bcc,$ARGS[$counter]);
                }
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-m$/) {                  ## Message ##
            $counter++;
            $message = "";
            while ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                if ($message) { $message .= " "; }
                $message .= $ARGS[$counter];
                $counter++;
            }   $counter--;
            
            ## Replace '\n' with $CRLF.
            ## This allows newlines with messages sent on the command line
            $message =~ s/\\n/$CRLF/g;
        }
        
        elsif ($ARGS[$counter] =~ /^-u$/) {                  ## Subject ##
            $counter++;
            $subject = "";
            while ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                if ($subject) { $subject .= " "; }
                $subject .= $ARGS[$counter];
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-s$/) {                  ## Server ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                $conf{'server'} = $ARGS[$counter];
                if ($conf{'server'} =~ /:/) {                ## Port ##
                    ($conf{'server'},$conf{'port'}) = split(":",$conf{'server'});
                }
            }
            else { printmsg("WARNING - The argument after -s was not the server!", 0); $counter--; }
        }

        elsif ($ARGS[$counter] =~ /^-b$/) {                  ## Bind Address ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
                $conf{'bindaddr'} = $ARGS[$counter];
            }
            else { printmsg("WARNING - The argument after -b was not the bindaddr!", 0); $counter--; }
        }
        
        elsif ($ARGS[$counter] =~ /^-a$/) {                  ## Attachments ##
            $counter++;
            while ($ARGS[$counter] && ($ARGS[$counter] !~ /^-/)) {
                push (@attachments,$ARGS[$counter]);
                $counter++;
            }   $counter--;
        }
        
        elsif ($ARGS[$counter] =~ /^-xu$/) {                  ## AuthSMTP Username ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
               $opt{'username'} = $ARGS[$counter];
            }
            else {
                printmsg("WARNING => The argument after -xu was not valid username!", 0);
                $counter--;
            }
        }
        
        elsif ($ARGS[$counter] =~ /^-xp$/) {                  ## AuthSMTP Password ##
            $counter++;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) {
               $opt{'password'} = $ARGS[$counter];
            }
            else {
                printmsg("WARNING => The argument after -xp was not valid password!", 0);
                $counter--;
            }
        }
        
        elsif ($ARGS[$counter] =~ /^-l$/) {                  ## Logging ##
            $counter++;
            $conf{'logging'} = 1;
            if ($ARGS[$counter] && $ARGS[$counter] !~ /^-/) { $conf{'logFile'} = $ARGS[$counter]; }
            else { printmsg("WARNING - The argument after -l was not the log file!", 0); $counter--; }
        }
        
        elsif ($ARGS[$counter] =~ s/^-v+//i) {               ## Verbosity ##
            my $tmp = (length($&) - 1);
            $conf{'debug'} += $tmp;
        }
        
        elsif ($ARGS[$counter] =~ /^-q$/) {                  ## Quiet ##
            $conf{'stdout'} = 0;
        }
        
        else {
            printmsg("Error: \"$ARGS[$counter]\" is not a recognized option!", 0);
            help();
        }
        
    }






    
    
    ###################################################
    ##  Verify required variables are set correctly  ##
    ###################################################
    
    ## Make sure we have something in $conf{hostname} and $opt{fqdn}
    if ($opt{'fqdn'} =~ /\./) {
        $conf{'hostname'} = $opt{'fqdn'};
        $conf{'hostname'} =~ s/\..*//;
    }
    
    if (!$conf{'server'}) { $conf{'server'} = 'localhost'; }
    if (!$conf{'port'})   { $conf{'port'} = 25; }
    if (!$from) {
        quit("ERROR => You must specify a 'from' field!  Try --help.", 1);
    }
    if ( ((scalar(@to)) + (scalar(@cc)) + (scalar(@bcc))) <= 0) {
        quit("ERROR => You must specify at least one recipient via -t, -cc, or -bcc", 1);
    }
    
    ## Make sure email addresses look OK.
    foreach my $addr (@to, @cc, @bcc, $from, $opt{'reply-to'}) {
        if ($addr) {
            if (!returnAddressParts($addr)) {
                printmsg("ERROR => Can't use improperly formatted email address: $addr", 0);
                printmsg("HINT => Try viewing the extended help on addressing with \"--help addressing\"", 1);
                quit("", 1);
            }
        }
    }
    
    ## Make sure all attachments exist.
    foreach my $file (@attachments) {
        if ( (! -f $file) or (! -r $file) ) {
            printmsg("ERROR => The attachment [$file] doesn't exist!", 0);
            printmsg("HINT => Try specifying the full path to the file or reading extended help with \"--help message\"", 1);
            quit("", 1);
        }
    }
    
    if ($conf{'logging'} and (!$conf{'logFile'})) {
        quit("ERROR => You used -l to enable logging but didn't specify a log file!", 1);
    }    
    
    if ( $opt{'username'} ) {
        if (!$opt{'password'}) {
            ## Prompt for a password since one wasn't specified with the -xp option.
            $SIG{'ALRM'} = sub { quit("ERROR => Timeout waiting for password inpupt", 1); };
            alarm(60) if ($^O !~ /win/i);  ## alarm() doesn't work in win32
            print "Password: ";
            $opt{'password'} = <STDIN>; chomp $opt{'password'};
            if (!$opt{'password'}) {
                quit("ERROR => A username for SMTP authentication was specified, but no password!", 1);
            }
        }
    }
    
    ## Validate the TLS setting
    $opt{'tls'} = lc($opt{'tls'});
    if ($opt{'tls'} !~ /^(auto|yes|no)$/) {
        quit("ERROR => Invalid TLS setting ($opt{'tls'}). Must be one of auto, yes, or no.", 1);
    }
    
    ## If TLS is set to "yes", make sure sendEmail loaded the libraries needed.
    if ($opt{'tls'} eq 'yes' and $conf{'tls_client'} == 0) {
        quit("ERROR => No TLS support!  SendEmail can't load required libraries. (try installing Net::SSLeay and IO::Socket::SSL)", 1);
    }
    
    ## Return 0 errors
    return(0);
}
















## getline($socketRef)
sub getline {
    my ($socketRef) = @_;
    local ($/) = "\r\n";
    return $$socketRef->getline;
}




## Receive a (multiline?) SMTP response from ($socketRef)
sub getResponse {
    my ($socketRef) = @_;
    my ($tmp, $reply);
    local ($/) = "\r\n";
    return undef unless defined($tmp = getline($socketRef));
    return("getResponse() socket is not open") unless ($$socketRef->opened);
    ## Keep reading lines if it's a multi-line response
    while ($tmp =~ /^\d{3}-/o) {
        $reply .= $tmp;
        return undef unless defined($tmp = getline($socketRef));
    }
    $reply .= $tmp;
    $reply =~ s/\r?\n$//o;
    return $reply;
}




###############################################################################################
##  Function:    SMTPchat ( [string $command] )
##
##  Description: Sends $command to the SMTP server (on SERVER) and awaits a successful
##               reply form the server.  If the server returns an error, or does not reply
##               within $conf{'alarm'} seconds an error is generated.
##               NOTE: $command is optional, if no command is specified then nothing will
##               be sent to the server, but a valid response is still required from the server.
##
##  Input:       [$command]          A (optional) valid SMTP command (ex. "HELO")
##  
##  
##  Output:      Returns zero on success, or non-zero on error.  
##               Error messages will be stored in $conf{'error'}
##               A copy of the last SMTP response is stored in the global variable
##               $conf{'SMTPchat_response'}
##               
##  
##  Example:     SMTPchat ("HELO mail.isp.net");
###############################################################################################
sub SMTPchat {
    my ($command) = @_;
    
    printmsg("INFO => Sending: \t$command", 1) if ($command);
    
    ## Send our command
    print $SERVER "$command$CRLF" if ($command);
    
    ## Read a response from the server
    $SIG{'ALRM'} = sub { $conf{'error'} = "alarm"; $SERVER->close(); };
    alarm($conf{'alarm'}) if ($^O !~ /win/i);  ## alarm() doesn't work in win32;
    my $result = $conf{'SMTPchat_response'} = getResponse(\$SERVER); 
    alarm(0) if ($^O !~ /win/i);  ## alarm() doesn't work in win32;
    
    ## Generate an alert if we timed out
    if ($conf{'error'} eq "alarm") {
        $conf{'error'} = "ERROR => Timeout while reading from $conf{'server'}:$conf{'port'} There was no response after $conf{'alarm'} seconds.";
        return(1);
    }
    
    ## Make sure the server actually responded
    if (!$result) {
        $conf{'error'} = "ERROR => $conf{'server'}:$conf{'port'} returned a zero byte response to our query.";
        return(2);
    }
    
    ## Validate the response
    if (evalSMTPresponse($result)) {
        ## conf{'error'} will already be set here
        return(2);
    }
    
    ## Print the success messsage
    printmsg($conf{'error'}, 1);
    
    ## Return Success
    return(0);
}












###############################################################################################
##  Function:    evalSMTPresponse (string $message )
##
##  Description: Searches $message for either an  SMTP success or error code, and returns
##               0 on success, and the actual error code on error.
##               
##
##  Input:       $message          Data received from a SMTP server (ex. "220 
##                                
##  
##  Output:      Returns zero on success, or non-zero on error.  
##               Error messages will be stored in $conf{'error'}
##               
##  
##  Example:     SMTPchat ("HELO mail.isp.net");
###############################################################################################
sub evalSMTPresponse {
    my ($message) = @_;
    
    ## Validate input
    if (!$message) { 
        $conf{'error'} = "ERROR => No message was passed to evalSMTPresponse().  What happened?";
        return(1)
    }
    
    printmsg("DEBUG => evalSMTPresponse() - Checking for SMTP success or error status in the message: $message ", 3);
    
    ## Look for a SMTP success code
    if ($message =~ /^([23]\d\d)/) {
        printmsg("DEBUG => evalSMTPresponse() - Found SMTP success code: $1", 2);
        $conf{'error'} = "SUCCESS => Received: \t$message";
        return(0);
    }
    
    ## Look for a SMTP error code
    if ($message =~ /^([45]\d\d)/) {
        printmsg("DEBUG => evalSMTPresponse() - Found SMTP error code: $1", 2);
        $conf{'error'} = "ERROR => Received: \t$message";
        return($1);
    }
    
    ## If no SMTP codes were found return an error of 1
    $conf{'error'} = "ERROR => Received a message with no success or error code. The message received was: $message";
    return(2);
    
}










#########################################################
# SUB: &return_month(0,1,etc)
#  returns the name of the month that corrosponds
#  with the number.  returns 0 on error.
#########################################################
sub return_month {
    my $x = $_[0];
    if ($x == 0)  { return 'Jan'; }
    if ($x == 1)  { return 'Feb'; }
    if ($x == 2)  { return 'Mar'; }
    if ($x == 3)  { return 'Apr'; }
    if ($x == 4)  { return 'May'; }
    if ($x == 5)  { return 'Jun'; }
    if ($x == 6)  { return 'Jul'; }
    if ($x == 7)  { return 'Aug'; }
    if ($x == 8)  { return 'Sep'; }
    if ($x == 9)  { return 'Oct'; }
    if ($x == 10) { return 'Nov'; }
    if ($x == 11) { return 'Dec'; }
    return (0);
}
















#########################################################
# SUB: &return_day(0,1,etc)
#  returns the name of the day that corrosponds
#  with the number.  returns 0 on error.
#########################################################
sub return_day {
    my $x = $_[0];
    if ($x == 0)  { return 'Sun'; }
    if ($x == 1)  { return 'Mon'; }
    if ($x == 2)  { return 'Tue'; }
    if ($x == 3)  { return 'Wed'; }
    if ($x == 4)  { return 'Thu'; }
    if ($x == 5)  { return 'Fri'; }
    if ($x == 6)  { return 'Sat'; }
    return (0);
}
















###############################################################################################
##  Function:    returnAddressParts(string $address)
##
##  Description: Returns a two element array containing the "Name" and "Address" parts of 
##               an email address.
##  
## Example:      "Brandon Zehm <caspian@dotconf.net>"
##               would return: ("Brandon Zehm", "caspian@dotconf.net");
## 
##               "caspian@dotconf.net"
##               would return: ("caspian@dotconf.net", "caspian@dotconf.net")
###############################################################################################
sub returnAddressParts {
    my $input = $_[0];
    my $name = "";
    my $address = "";
    
    ## Make sure to fail if it looks totally invalid
    if ($input !~ /(\S+\@\S+)/) {
        $conf{'error'} = "ERROR => The address [$input] doesn't look like a valid email address, ignoring it";
        return(undef());
    }
    
    ## Check 1, should find addresses like: "Brandon Zehm <caspian@dotconf.net>"
    elsif ($input =~ /^\s*(\S(.*\S)?)\s*<(\S+\@\S+)>/o) {
        ($name, $address) = ($1, $3);
    }
    
    ## Otherwise if that failed, just get the address: <caspian@dotconf.net>
    elsif ($input =~ /<(\S+\@\S+)>/o) {
        $name = $address = $1;
    }
    
    ## Or maybe it was formatted this way: caspian@dotconf.net
    elsif ($input =~ /(\S+\@\S+)/o) {
        $name = $address = $1;
    }
    
    ## Something stupid happened, just return an error.
    unless ($name and $address) {
        printmsg("ERROR => Couldn't parse the address: $input", 0);
        printmsg("HINT => If you think this should work, consider reporting this as a bug to $conf{'authorEmail'}", 1);
        return(undef());
    }
    
    ## Make sure there aren't invalid characters in the address, and return it.
    my $ctrl        = '\000-\037';
    my $nonASCII    = '\x80-\xff';
    if ($address =~ /[<> ,;:"'\[\]\\$ctrl$nonASCII]/) {
        printmsg("WARNING => The address [$address] seems to contain invalid characters: continuing anyway", 0);
    }
    return($name, $address);
}
















###############################################################################################
##  Function:    base64_encode(string $data)
##
##  Description: Returns $data as a base64 encoded string
##               If the encoded data is returned in 76 character long lines with the final 
##               CR\LF removed.
###############################################################################################
sub base64_encode {
    my $data = $_[0];
    my $tmp = '';
    my $base64 = '';
    my $CRLF = "\r\n";
    
    ###################################
    ## Convert binary data to base64 ##
    ###################################
    while ($data =~ s/(.{45})//s) {        ## Get 45 bytes from the binary string
        $tmp = substr(pack('u', $&), 1);   ## Convert the binary to uuencoded text
        chop($tmp);
        $tmp =~ tr|` -_|AA-Za-z0-9+/|;     ## Translate from uuencode to base64
        $base64 .= $tmp;
    }
    
    ###################################
    ## Encode and send the leftovers ##
    ###################################
    my $padding = "";
    if ( ($data) and (length($data) >= 1) ) {
        $padding = (3 - length($data) % 3) % 3;    ## Set flag if binary data isn't divisible by 3
        $tmp = substr(pack('u', $data), 1);       ## Convert the binary to uuencoded text
        chop($tmp);
        $tmp =~ tr|` -_|AA-Za-z0-9+/|;            ## Translate from uuencode to base64
        $base64 .= $tmp;
    }
    
    ############################
    ## Fix padding at the end ##
    ############################
    $data = '';
    $base64 =~ s/.{$padding}$/'=' x $padding/e if $padding; ## Fix the end padding if flag (from above) is set
    while ($base64 =~ s/(.{1,76})//s) {                     ## Put $CRLF after each 76 characters
        $data .= "$1$CRLF";
    }
    chomp $data;
    
    return($data);
}









#########################################################
# SUB: send_attachment("/path/filename")
# Sends the mime headers and base64 encoded file
# to the email server.
#########################################################
sub send_attachment {
    my ($filename) = @_;                             ## Get filename passed
    my (@fields, $y, $filename_name, $encoding,      ## Local variables
        @attachlines, $content_type);
    my $bin = 1;
    
    @fields = split(/\/|\\/, $filename);             ## Get the actual filename without the path  
    $filename_name = pop(@fields);       
    push @attachments_names, $filename_name;         ## FIXME: This is only used later for putting in the log file
    
    ##########################
    ## Autodetect Mime Type ##
    ##########################
    
    @fields = split(/\./, $filename_name);
    $encoding = $fields[$#fields];
    
    if ($encoding =~ /txt|text|log|conf|^c$|cpp|^h$|inc|m3u/i) {   $content_type = 'text/plain';                      }
    elsif ($encoding =~ /html|htm|shtml|shtm|asp|php|cfm/i) {      $content_type = 'text/html';                       }
    elsif ($encoding =~ /sh$/i) {                                  $content_type = 'application/x-sh';                }
    elsif ($encoding =~ /tcl/i) {                                  $content_type = 'application/x-tcl';               }
    elsif ($encoding =~ /pl$/i) {                                  $content_type = 'application/x-perl';              }
    elsif ($encoding =~ /js$/i) {                                  $content_type = 'application/x-javascript';        }
    elsif ($encoding =~ /man/i) {                                  $content_type = 'application/x-troff-man';         }
    elsif ($encoding =~ /gif/i) {                                  $content_type = 'image/gif';                       }
    elsif ($encoding =~ /jpg|jpeg|jpe|jfif|pjpeg|pjp/i) {          $content_type = 'image/jpeg';                      }
    elsif ($encoding =~ /tif|tiff/i) {                             $content_type = 'image/tiff';                      }
    elsif ($encoding =~ /xpm/i) {                                  $content_type = 'image/x-xpixmap';                 }
    elsif ($encoding =~ /bmp/i) {                                  $content_type = 'image/x-MS-bmp';                  }
    elsif ($encoding =~ /pcd/i) {                                  $content_type = 'image/x-photo-cd';                }
    elsif ($encoding =~ /png/i) {                                  $content_type = 'image/png';                       }
    elsif ($encoding =~ /aif|aiff/i) {                             $content_type = 'audio/x-aiff';                    }
    elsif ($encoding =~ /wav/i) {                                  $content_type = 'audio/x-wav';                     }
    elsif ($encoding =~ /mp2|mp3|mpa/i) {                          $content_type = 'audio/x-mpeg';                    }
    elsif ($encoding =~ /ra$|ram/i) {                              $content_type = 'audio/x-pn-realaudio';            }
    elsif ($encoding =~ /mpeg|mpg/i) {                             $content_type = 'video/mpeg';                      }
    elsif ($encoding =~ /mov|qt$/i) {                              $content_type = 'video/quicktime';                 }
    elsif ($encoding =~ /avi/i) {                                  $content_type = 'video/x-msvideo';                 }
    elsif ($encoding =~ /zip/i) {                                  $content_type = 'application/x-zip-compressed';    }
    elsif ($encoding =~ /tar/i) {                                  $content_type = 'application/x-tar';               }
    elsif ($encoding =~ /jar/i) {                                  $content_type = 'application/java-archive';        }
    elsif ($encoding =~ /exe|bin/i) {                              $content_type = 'application/octet-stream';        }
    elsif ($encoding =~ /ppt|pot|ppa|pps|pwz/i) {                  $content_type = 'application/vnd.ms-powerpoint';   }
    elsif ($encoding =~ /mdb|mda|mde/i) {                          $content_type = 'application/vnd.ms-access';       }
    elsif ($encoding =~ /xls|xlt|xlm|xld|xla|xlc|xlw|xll/i) {      $content_type = 'application/vnd.ms-excel';        }
    elsif ($encoding =~ /doc|dot/i) {                              $content_type = 'application/msword';              }
    elsif ($encoding =~ /rtf/i) {                                  $content_type = 'application/rtf';                 }
    elsif ($encoding =~ /pdf/i) {                                  $content_type = 'application/pdf';                 }
    elsif ($encoding =~ /tex/i) {                                  $content_type = 'application/x-tex';               }
    elsif ($encoding =~ /latex/i) {                                $content_type = 'application/x-latex';             }
    elsif ($encoding =~ /vcf/i) {                                  $content_type = 'application/x-vcard';             }
    else { $content_type = 'application/octet-stream';  }
  
  
  ############################
  ## Process the attachment ##
  ############################
    
    #####################################
    ## Generate and print MIME headers ##
    #####################################
    
    $y  = "$CRLF--$conf{'delimiter'}$CRLF";
    $y .= "Content-Type: $content_type;$CRLF";
    $y .= "        name=\"$filename_name\"$CRLF";
    $y .= "Content-Transfer-Encoding: base64$CRLF";
    $y .= "Content-Disposition: attachment; filename=\"$filename_name\"$CRLF";
    $y .= "$CRLF";
    print $SERVER $y;
    
    
    ###########################################################
    ## Convert the file to base64 and print it to the server ##
    ###########################################################
    
    open (FILETOATTACH, $filename) || do { 
        printmsg("ERROR => Opening the file [$filename] for attachment failed with the error: $!", 0);
        return(1);
    };
    binmode(FILETOATTACH);                 ## Hack to make Win32 work
    
    my $res = "";
    my $tmp = "";
    my $base64 = "";
    while (<FILETOATTACH>) {               ## Read a line from the (binary) file
        $res .= $_;
        
        ###################################
        ## Convert binary data to base64 ##
        ###################################
        while ($res =~ s/(.{45})//s) {         ## Get 45 bytes from the binary string
            $tmp = substr(pack('u', $&), 1);   ## Convert the binary to uuencoded text
            chop($tmp);
            $tmp =~ tr|` -_|AA-Za-z0-9+/|;     ## Translate from uuencode to base64
            $base64 .= $tmp;
        }
        
        ################################
        ## Print chunks to the server ##
        ################################
        while ($base64 =~ s/(.{76})//s) {
            print $SERVER "$1$CRLF";
        }
      
    }
    
    ###################################
    ## Encode and send the leftovers ##
    ###################################
    my $padding = "";
    if ( ($res) and (length($res) >= 1) ) {
        $padding = (3 - length($res) % 3) % 3;  ## Set flag if binary data isn't divisible by 3
        $res = substr(pack('u', $res), 1);      ## Convert the binary to uuencoded text
        chop($res);
        $res =~ tr|` -_|AA-Za-z0-9+/|;          ## Translate from uuencode to base64
    }
    
    ############################
    ## Fix padding at the end ##
    ############################
    $res = $base64 . $res;                               ## Get left overs from above
    $res =~ s/.{$padding}$/'=' x $padding/e if $padding; ## Fix the end padding if flag (from above) is set
    if ($res) {
        while ($res =~ s/(.{1,76})//s) {                 ## Send it to the email server.
            print $SERVER "$1$CRLF";
        }
    }
    
    close (FILETOATTACH) || do {
        printmsg("ERROR - Closing the filehandle for file [$filename] failed with the error: $!", 0);
        return(2);
    };
    
    ## Return 0 errors
    return(0);

}









###############################################################################################
##  Function:    $string = get_hostname (boot $fqdn)
##  
##  Description: Tries really hard to returns the short (or FQDN) hostname of the current
##               system.  Uses techniques and code from the  Sys-Hostname module.
##  
##  Input:       $fqdn     A true value (1) will cause this function to return a FQDN hostname
##                         rather than a short hostname.
##  
##  Output:      Returns a string
###############################################################################################
sub get_hostname {
    ## Assign incoming parameters to variables
    my ( $fqdn ) = @_;
    my $hostname = "";
    
    ## STEP 1: Get short hostname
    
    ## Load Sys::Hostname if it's available
    eval { require Sys::Hostname; };
    unless ($@) {
        $hostname = Sys::Hostname::hostname(); 
    }
    
    ## If that didn't get us a hostname, try a few other things
    else {
        ## Windows systems
        if ($^O !~ /win/i) {
            if ($ENV{'COMPUTERNAME'}) { $hostname = $ENV{'COMPUTERNAME'}; }
            if (!$hostname) { $hostname = gethostbyname('localhost'); }
            if (!$hostname) { chomp($hostname = `hostname 2> NUL`) };
        }
        
        ## Unix systems
        else {
            local $ENV{PATH} = '/usr/bin:/bin:/usr/sbin:/sbin';  ## Paranoia
            
            ## Try the environment first (Help!  What other variables could/should I be checking here?)
            if ($ENV{'HOSTNAME'}) { $hostname = $ENV{'HOSTNAME'}; }
            
            ## Try the hostname command
            eval { local $SIG{__DIE__}; local $SIG{CHLD}; $hostname = `hostname 2>/dev/null`; chomp($hostname); } ||
            
            ## Try POSIX::uname(), which strictly can't be expected to be correct
            eval { local $SIG{__DIE__}; require POSIX; $hostname = (POSIX::uname())[1]; } ||
            
            ## Try the uname command
            eval { local $SIG{__DIE__}; $hostname = `uname -n 2>/dev/null`; chomp($hostname); };
            
        }
        
        ## If we can't find anything else, return ""
        if (!$hostname) {
            print "WARNING => No hostname could be determined, please specify one with -o fqdn=FQDN option!\n";
            return("unknown");
        }
    }
    
    ## Return the short hostname
    unless ($fqdn) {
        $hostname =~ s/\..*//;
        return(lc($hostname));
    }
    
    ## STEP 2: Determine the FQDN
    
    ## First, if we already have one return it.
    if ($hostname =~ /\w\.\w/) { return(lc($hostname)); }
    
    ## Next try using 
    eval { $fqdn = (gethostbyname($hostname))[0]; };
    if ($fqdn) { return(lc($fqdn)); }
    return(lc($hostname));
}








###############################################################################################
##  Function:    printmsg (string $message, int $level)
##
##  Description: Handles all messages - printing them to the screen only if the messages
##               $level is >= the global debug level.  If $conf{'logFile'} is defined it
##               will also log the message to that file.
##
##  Input:       $message          A message to be printed, logged, etc.
##               $level            The debug level of the message. If
##                                 not defined 0 will be assumed.  0 is
##                                 considered a normal message, 1 and 
##                                 higher is considered a debug message.
##  
##  Output:      Prints to STDOUT
##
##  Assumptions: $conf{'hostname'} should be the name of the computer we're running on.
##               $conf{'stdout'} should be set to 1 if you want to print to stdout
##               $conf{'logFile'} should be a full path to a log file if you want that
##               $conf{'syslog'} should be 1 if you want to syslog, the syslog() function
##               written by Brandon Zehm should be present.
##               $conf{'debug'} should be an integer between 0 and 10.
##
##  Example:     printmsg("WARNING: We believe in generic error messages... NOT!", 0);
###############################################################################################
sub printmsg {
    ## Assign incoming parameters to variables
    my ( $message, $level ) = @_;
    
    ## Make sure input is sane
    $level = 0 if (!defined($level));
    $message =~ s/\s+$//sgo;
    $message =~ s/\r?\n/, /sgo;
    
    ## Continue only if the debug level of the program is >= message debug level.
    if ($conf{'debug'} >= $level) {
        
        ## Get the date in the format: Dec  3 11:14:04
        my ($sec, $min, $hour, $mday, $mon) = localtime();
        $mon = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[$mon];
        my $date = sprintf("%s %02d %02d:%02d:%02d", $mon, $mday, $hour, $min, $sec);
        
        ## Print to STDOUT always if debugging is enabled, or if conf{stdout} is true.
        if ( ($conf{'debug'} >= 1) or ($conf{'stdout'} == 1) ) {
            print "$date $conf{'hostname'} $conf{'programName'}\[$$\]: $message\n";
        }
        
        ## Print to the log file if $conf{'logging'} is true
        if ($conf{'logFile'}) {
            if (openLogFile($conf{'logFile'})) { $conf{'logFile'} = ""; printmsg("ERROR => Opening the file [$conf{'logFile'}] for appending returned the error: $!", 1); }
            print LOGFILE "$date $conf{'hostname'} $conf{'programName'}\[$$\]: $message\n";
        }
        
    }
    
    ## Return 0 errors
    return(0);
}












###############################################################################################
## FUNCTION:    
##   openLogFile ( $filename )
## 
## 
## DESCRIPTION: 
##   Opens the file $filename and attaches it to the filehandle "LOGFILE".  Returns 0 on success
##   and non-zero on failure.  Error codes are listed below, and the error message gets set in
##   global variable $!.
##   
##   
## Example: 
##   openFile ("/var/log/sendEmail.log");
##
###############################################################################################
sub openLogFile {
    ## Get the incoming filename
    my $filename = $_[0];
    
    ## Make sure our file exists, and if the file doesn't exist then create it
    if ( ! -f $filename ) {
        print STDERR "NOTICE: The log file [$filename] does not exist.  Creating it now with mode [0600].\n" if ($conf{'stdout'});
        open (LOGFILE, ">>$filename");
        close LOGFILE;
        chmod (0600, $filename);
    }
    
    ## Now open the file and attach it to a filehandle
    open (LOGFILE,">>$filename") or return (1);
    
    ## Put the file into non-buffering mode
    select LOGFILE;
    $| = 1;
    select STDOUT;
    
    ## Return success
    return(0);
}








###############################################################################################
##  Function:    read_file (string $filename)
##  
##  Description: Reads the contents of a file and returns a two part array:
##               ($status, $file-contents)
##               $status is 0 on success, non-zero on error.
##               
##  Example:     ($status, $file) = read_file)("/etc/passwd");
###############################################################################################
sub read_file {
    my ( $filename ) = @_;
    
    ## If the value specified is a file, load the file's contents
    if ( (-e $filename and -r $filename) ) {
        my $FILE;
        if(!open($FILE, ' ' . $filename)) {
            return((1, ""));
        }
        my $file = '';
        while (<$FILE>) {
            $file .= $_;
        }
        ## Strip an ending \r\n
        $file =~ s/\r?\n$//os;
    }
    return((1, ""));
}









###############################################################################################
##  Function:    quit (string $message, int $errorLevel)
##  
##  Description: Exits the program, optionally printing $message.  It 
##               returns an exit error level of $errorLevel to the 
##               system  (0 means no errors, and is assumed if empty.)
##
##  Example:     quit("Exiting program normally", 0);
###############################################################################################
sub quit {
    my ( $message, $errorLevel ) = @_;
    $errorLevel = 0 if (!defined($errorLevel));
    
    ## Print exit message
    if ($message) { 
        printmsg($message, 0);
    }
    
    ## Exit
    exit($errorLevel);
}












###############################################################################################
## Function:    help ()
##
## Description: For all those newbies ;) 
##              Prints a help message and exits the program.
## 
###############################################################################################
sub help {
exit(1) if (!$conf{'stdout'});
print <<EOM;

${colorBold}$conf{'programName'}-$conf{'version'} by $conf{'authorName'} <$conf{'authorEmail'}>${colorNoBold}

Synopsis:  $conf{'programName'} -f ADDRESS [options]
  
  ${colorRed}Required:${colorNormal}
    -f ADDRESS                from (sender) email address
    * At least one recipient required via -t, -cc, or -bcc
    * Message body required via -m, STDIN, or -o message-file=FILE
    
  ${colorGreen}Common:${colorNormal}
    -t ADDRESS [ADDR ...]     to email address(es)
    -u SUBJECT                message subject
    -m MESSAGE                message body
    -s SERVER[:PORT]          smtp mail relay, default is $conf{'server'}:$conf{'port'}
    
  ${colorGreen}Optional:${colorNormal}
    -a   FILE [FILE ...]      file attachment(s)
    -cc  ADDRESS [ADDR ...]   cc  email address(es)
    -bcc ADDRESS [ADDR ...]   bcc email address(es)
    -xu  USERNAME             username for SMTP authentication
    -xp  PASSWORD             password for SMTP authentication
    
  ${colorGreen}Paranormal:${colorNormal}
    -b BINDADDR[:PORT]        local host bind address
    -l LOGFILE                log to the specified file
    -v                        verbosity, use multiple times for greater effect
    -q                        be quiet (i.e. no STDOUT output)
    -o NAME=VALUE             advanced options, for details try: --help misc
        -o message-file=FILE         -o message-format=raw
        -o message-header=HEADER     -o message-charset=CHARSET
        -o reply-to=ADDRESS          -o timeout=SECONDS
        -o username=USERNAME         -o password=PASSWORD
        -o tls=<auto|yes|no>         -o fqdn=FQDN
  
  ${colorGreen}Help:${colorNormal}
    --help                    the helpful overview you're reading now
    --help addressing         explain addressing and related options
    --help message            explain message body input and related options
    --help networking         explain -s, -b, etc
    --help output             explain logging and other output options
    --help misc               explain -o options, TLS, SMTP auth, and more

EOM
exit(1);
}









###############################################################################################
## Function:    helpTopic ($topic)
##
## Description: For all those newbies ;) 
##              Prints a help message and exits the program.
## 
###############################################################################################
sub helpTopic {
    exit(1) if (!$conf{'stdout'});
    my ($topic) = @_;

    CASE: {




## ADDRESSING
        ($topic eq 'addressing') && do {
            print <<EOM;

${colorBold}ADDRESSING DOCUMENTATION${colorNormal}

${colorGreen}Addressing Options${colorNormal}
Options related to addressing:
    -f   ADDRESS
    -t   ADDRESS [ADDRESS ...]
    -cc  ADDRESS [ADDRESS ...]
    -bcc ADDRESS [ADDRESS ...]
    -o   reply-to=ADDRESS
    
-f ADDRESS
    This required option specifies who the email is from, I.E. the sender's
    email address.
    
-t ADDRESS [ADDRESS ...]
    This option specifies the primary recipient(s).  At least one recipient
    address must be specified via the -t, -cc. or -bcc options.

-cc ADDRESS [ADDRESS ...]
    This option specifies the "carbon copy" recipient(s).  At least one 
    recipient address must be specified via the -t, -cc. or -bcc options.

-bcc ADDRESS [ADDRESS ...]
    This option specifies the "blind carbon copy" recipient(s).  At least
    one recipient address must be specified via the -t, -cc. or -bcc options.

-o reply-to=ADDRESS
    This option specifies that an optional "Reply-To" address should be
    written in the email's headers.
    

${colorGreen}Email Address Syntax${colorNormal}
Email addresses may be specified in one of two ways:
    Full Name:     "John Doe <john.doe\@gmail.com>"
    Just Address:  "john.doe\@gmail.com"

The "Full Name" method is useful if you want a name, rather than a plain
email address, to be displayed in the recipient's From, To, or Cc fields
when they view the message.
    

${colorGreen}Multiple Recipients${colorNormal}
The -t, -cc, and -bcc options each accept multiple addresses.  They may be
specified by separating them by either a white space, comma, or semi-colon
separated list.  You may also specify the -t, -cc, and -bcc options multiple
times, each occurance will append the new recipients to the respective list.

Examples:
(I used "-t" in these examples, but it can be "-cc" or "-bcc" as well)

  * Space separated list:
    -t jane.doe\@yahoo.com "John Doe <john.doe\@gmail.com>"
    
  * Semi-colon separated list:
    -t "jane.doe\@yahoo.com; John Doe <john.doe\@gmail.com>"
 
  * Comma separated list:
    -t "jane.doe\@yahoo.com, John Doe <john.doe\@gmail.com>"
  
  * Multiple -t, -cc, or -bcc options:
    -t "jane.doe\@yahoo.com" -t "John Doe <john.doe\@gmail.com>"
  

EOM
            last CASE;
        };






## MESSAGE
        ($topic eq 'message') && do {
            print <<EOM;

${colorBold}MESSAGE DOCUMENTATION${colorNormal}

${colorGreen}Message Options${colorNormal}
Options related to the email message body:
    -u  SUBJECT
    -m  MESSAGE
    -o  message-file=FILE
    -o  message-header=EMAIL HEADER
    -o  message-charset=CHARSET
    -o  message-format=raw
    
-u SUBJECT
    This option allows you to specify the subject for your email message.
    It is not required (anymore) that the subject be quoted, although it 
    is recommended.  The subject will be read until an argument starting
    with a hyphen (-) is found.  
    Examples:
      -u "Contact information while on vacation"
      -u New Microsoft vulnerability discovered

-m MESSAGE
    This option is one of three methods that allow you to specify the message
    body for your email.  The message may be specified on the command line
    with this -m option, read from a file with the -o message-file=FILE
    option, or read from STDIN if neither of these options are present.
    
    It is not required (anymore) that the message be quoted, although it is
    recommended.  The message will be read until an argument starting with a
    hyphen (-) is found.
    Examples:
      -m "See you in South Beach, Hawaii.  -Todd"
      -m Please ensure that you upgrade your systems right away
    
    Multi-line message bodies may be specified with the -m option by putting
    a "\\n" into the message.  Example:
      -m "This is line 1.\\nAnd this is line 2."
    
    HTML messages are supported, simply begin your message with "<html>" and
    sendEmail will properly label the mime header so MUAs properly render
    the message.  It is currently not possible without "-o message-format=raw"
    to send a message with both text and html parts with sendEmail.

-o message-file=FILE
    This option is one of three methods that allow you to specify the message
    body for your email.  To use this option simply specify a text file
    containing the body of your email message. Examples:
      -o message-file=/root/message.txt
      -o message-file="C:\\Program Files\\output.txt"

-o message-header=EMAIL HEADER
    This option allows you to specify additional email headers to be included.
    To add more than one message header simply use this option on the command
    line more than once.  If you specify a message header that sendEmail would
    normally generate the one you specified will be used in it's place.  
    Do not use this unless you know what you are doing!
    Example: 
      To scare a Microsoft Outlook user you may want to try this:
      -o message-header="X-Message-Flag: Message contains illegal content"
    Example: 
      To request a read-receipt try this:
      -o message-header="Disposition-Notification-To: <user\@domain.com>"
    Example: 
      To set the message priority try this:
      -o message-header="X-Priority: 1"
      Priority reference: 1=highest, 2=high, 3=normal, 4=low, 5=lowest
    
-o message-charset=CHARSET
    This option allows you to specify the character-set for the message body.
    The default is iso-8859-1.
    
-o message-format=raw
    This option instructs sendEmail to assume the message (specified with -m,
    read from STDIN, or read from the file specified in -o message-file=FILE)
    is already a *complete* email message.  SendEmail will not generate any
    headers and will transmit the message as-is to the remote SMTP server.
    Due to the nature of this option the following command line options will
    be ignored when this one is used:
      -u SUBJECT
      -o message-header=EMAIL HEADER
      -o message-charset=CHARSET
      -a ATTACHMENT
      

${colorGreen}The Message Body${colorNormal}
The email message body may be specified in one of three ways:
 1) Via the -m MESSAGE command line option.
    Example:
      -m "This is the message body"
      
 2) By putting the message body in a file and using the -o message-file=FILE
    command line option.
    Example:
      -o message-file=/root/message.txt
      
 3) By piping the message body to sendEmail when nither of the above command
    line options were specified.
    Example:
      grep "ERROR" /var/log/messages | sendEmail -t you\@domain.com ...

If the message body begins with "<html>" then the message will be treated as
an HTML message and the MIME headers will be written so that a HTML capable
email client will display the message in it's HTML form.
Any of the above methods may be used with the -o message-format=raw option 
to deliver an already complete email message.


EOM
            last CASE;
        };
        





## MISC
        ($topic eq 'misc') && do {
            print <<EOM;

${colorBold}MISC DOCUMENTATION${colorNormal}

${colorGreen}Misc Options${colorNormal}
Options that don't fit anywhere else:
    -a   ATTACHMENT [ATTACHMENT ...]
    -xu  USERNAME
    -xp  PASSWORD
    -o   username=USERNAME
    -o   password=PASSWORD
    -o   tls=<auto|yes|no>
    -o   timeout=SECONDS
    -o   fqdn=FQDN
    
-a   ATTACHMENT [ATTACHMENT ...]
    This option allows you to attach any number of files to your email message.
    To specify more than one attachment, simply separate each filename with a
    space.  Example: -a file1.txt file2.txt file3.txt
    
-xu  USERNAME
    Alias for -o username=USERNAME
    
-xp  PASSWORD
    Alias for -o password=PASSWORD
    
-o   username=USERNAME (synonym for -xu)
    These options allow specification of a username to be used with SMTP
    servers that require authentication.  If a username is specified but a
    password is not, you will be prompted to enter one at runtime.

-o   password=PASSWORD (synonym for -xp)
    These options allow specification of a password to be used with SMTP
    servers that require authentication.  If a username is specified but a
    password is not, you will be prompted to enter one at runtime. 

-o   tls=<auto|yes|no>
    This option allows you to specify if TLS (SSL for SMTP) should be enabled
    or disabled.  The default, auto, will use TLS automatically if your perl
    installation has the IO::Socket::SSL and Net::SSLeay modules available,
    and if the remote SMTP server supports TLS.  To require TLS for message
    delivery set this to yes.  To disable TLS support set this to no.  A debug
    level of one or higher will reveal details about the status of TLS.
    
-o   timeout=SECONDS    
    This option sets the timeout value in seconds used for all network reads,
    writes, and a few other things.

-o   fqdn=FQDN    
    This option sets the Fully Qualified Domain Name used during the initial
    SMTP greeting.  Normally this is automatically detected, but in case you
    need to manually set it for some reason or get a warning about detection
    failing, you can use this to override the default.
    

EOM
            last CASE;
        };
        





## NETWORKING
        ($topic eq 'networking') && do {
            print <<EOM;

${colorBold}NETWORKING DOCUMENTATION${colorNormal}

${colorGreen}Networking Options${colorNormal}
Options related to networking:
    -s   SERVER[:PORT]
    -b   BINDADDR[:PORT]
    -o   tls=<auto|yes|no>
    -o   timeout=SECONDS
    
-s SERVER[:PORT]
    This option allows you to specify the SMTP server sendEmail should
    connect to to deliver your email message to.  If this option is not
    specified sendEmail will try to connect to localhost:25 to deliver
    the message.  THIS IS MOST LIKELY NOT WHAT YOU WANT, AND WILL LIKELY
    FAIL unless you have a email server (commonly known as an MTA) running
    on your computer!
    Typically you will need to specify your company or ISP's email server.
    For example, if you use CableOne you will need to specify:
       -s mail.cableone.net
    If you have your own email server running on port 300 you would
    probably use an option like this:
       -s myserver.mydomain.com:300

-b BINDADDR[:PORT]
    This option allows you to specify the local IP address (and optional
    tcp port number) for sendEmail to bind to when connecting to the remote
    SMTP server.  This useful for people who need to send an email from a
    specific network interface or source address and are running sendEmail on
    a firewall or other host with several network interfaces.

-o   tls=<auto|yes|no>
    This option allows you to specify if TLS (SSL for SMTP) should be enabled
    or disabled.  The default, auto, will use TLS automatically if your perl
    installation has the IO::Socket::SSL and Net::SSLeay modules available,
    and if the remote SMTP server supports TLS.  To require TLS for message
    delivery set this to yes.  To disable TLS support set this to no.  A debug
    level of one or higher will reveal details about the status of TLS.
    
-o timeout=SECONDS    
    This option sets the timeout value in seconds used for all network reads,
    writes, and a few other things.

    
EOM
            last CASE;
        };
        
        
        
        
        
        
## OUTPUT
        ($topic eq 'output') && do {
            print <<EOM;

${colorBold}OUTPUT DOCUMENTATION${colorNormal}

${colorGreen}Output Options${colorNormal}
Options related to output:
    -l LOGFILE
    -v
    -q
    
-l LOGFILE
    This option allows you to specify a log file to append to.  Every message
    that is displayed to STDOUT is also written to the log file.  This may be
    used in conjunction with -q and -v.

-q
    This option tells sendEmail to disable printing to STDOUT.  In other
    words nothing will be printed to the console.  This does not affect the
    behavior of the -l or -v options.
    
-v
    This option allows you to increase the debug level of sendEmail.  You may
    either use this option more than once, or specify more than one v at a
    time to obtain a debug level higher than one.  Examples:
        Specifies a debug level of 1:  -v
        Specifies a debug level of 2:  -vv
        Specifies a debug level of 2:  -v -v
    A debug level of one is recommended when doing any sort of debugging.  
    At that level you will see the entire SMTP transaction (except the
    body of the email message), and hints will be displayed for most
    warnings and errors.  The highest debug level is three.

    
EOM
            last CASE;
        };
        
        ## Unknown option selected!
        quit("ERROR => The help topic specified is not valid!", 1);
    };
    
exit(1);
}






















#############################
##                          ##
##      MAIN PROGRAM         ##
##                          ##
#############################


## Initialize
initialize();

## Process Command Line
processCommandLine();
$conf{'alarm'} = $opt{'timeout'};

## Abort program after $conf{'alarm'} seconds to avoid infinite hangs
alarm($conf{'alarm'}) if ($^O !~ /win/i);  ## alarm() doesn't work in win32




###################################################
##  Read $message from STDIN if -m was not used  ##
###################################################

if (!($message)) {
    ## Read message body from a file specified with -o message-file=
    if ($opt{'message-file'}) {
        if (! -e $opt{'message-file'}) {
            printmsg("ERROR => Message body file specified [$opt{'message-file'}] does not exist!", 0);
            printmsg("HINT => 1) check spelling of your file; 2) fully qualify the path; 3) doubble quote it", 1);
            quit("", 1);
        }
        if (! -r $opt{'message-file'}) {
            printmsg("ERROR => Message body file specified can not be read due to restricted permissions!", 0);
            printmsg("HINT => Check permissions on file specified to ensure it can be read", 1);
            quit("", 1);
        }
        if (!open(MFILE, "< " . $opt{'message-file'})) {
            printmsg("ERROR => Error opening message body file [$opt{'message-file'}]: $!", 0);
            quit("", 1);
        }
        while (<MFILE>) {
            $message .= $_;
        }
        close(MFILE);
    }
    
    ## Read message body from STDIN
    else {
        alarm($conf{'alarm'}) if ($^O !~ /win/i);  ## alarm() doesn't work in win32
        if ($conf{'stdout'}) {
            print "Reading message body from STDIN because the '-m' option was not used.\n";
            print "If you are manually typing in a message:\n";
            print "  - First line must be received within $conf{'alarm'} seconds.\n" if ($^O !~ /win/i);
            print "  - End manual input with a CTRL-D on its own line.\n\n" if ($^O !~ /win/i);
            print "  - End manual input with a CTRL-Z on its own line.\n\n" if ($^O =~ /win/i);
        }
        while (<STDIN>) {                 ## Read STDIN into $message
            $message .= $_;
            alarm(0) if ($^O !~ /win/i);  ## Disable the alarm since at least one line was received
        }
        printmsg("Message input complete.", 0);
    }
}

## Replace bare LF's with CRLF's (\012 should always have \015 with it)
$message =~ s/(\015)?(\012|$)/\015\012/g;

## Replace bare CR's with CRLF's (\015 should always have \012 with it)
$message =~ s/(\015)(\012|$)?/\015\012/g;

## Check message for bare periods and encode them
$message =~ s/(^|$CRLF)(\.{1})($CRLF|$)/$1.$2$3/g;

## Get the current date for the email header
my ($sec,$min,$hour,$mday,$mon,$year,$day) = gmtime();
$year += 1900; $mon = return_month($mon); $day = return_day($day);
my $date = sprintf("%s, %s %s %d %.2d:%.2d:%.2d %s",$day, $mday, $mon, $year, $hour, $min, $sec, $conf{'timezone'});




##################################
##  Connect to the SMTP server  ##
##################################
printmsg("DEBUG => Connecting to $conf{'server'}:$conf{'port'}", 1);
$SIG{'ALRM'} = sub { 
    printmsg("ERROR => Timeout while connecting to $conf{'server'}:$conf{'port'}  There was no response after $conf{'alarm'} seconds.", 0); 
    printmsg("HINT => Try specifying a different mail relay with the -s option.", 1);
    quit("", 1);
};
alarm($conf{'alarm'}) if ($^O !~ /win/i);  ## alarm() doesn't work in win32;
$SERVER = IO::Socket::INET->new( PeerAddr  => $conf{'server'},
                                 PeerPort  => $conf{'port'},
                                 LocalAddr => $conf{'bindaddr'},
                                 Proto     => 'tcp',
                                 Autoflush => 1,
                                 timeout   => $conf{'alarm'},
);
alarm(0) if ($^O !~ /win/i);  ## alarm() doesn't work in win32;

## Make sure we got connected
if ( (!$SERVER) or (!$SERVER->opened()) ) {
    printmsg("ERROR => Connection attempt to $conf{'server'}:$conf{'port'} failed: $@", 0);
    printmsg("HINT => Try specifying a different mail relay with the -s option.", 1);
    quit("", 1);
}

## Save our IP address for later
$conf{'ip'} = $SERVER->sockhost();
printmsg("DEBUG => My IP address is: $conf{'ip'}", 1);







#########################
##  Do the SMTP Dance  ##
#########################

## Read initial greeting to make sure we're talking to a live SMTP server
if (SMTPchat()) { quit($conf{'error'}, 1); }

## We're about to use $opt{'fqdn'}, make sure it isn't empty
if (!$opt{'fqdn'}) {
    ## Ok, that means we couldn't get a hostname, how about using the IP address for the HELO instead
    $opt{'fqdn'} = "[" . $conf{'ip'} . "]";
}

## EHLO
if (SMTPchat('EHLO ' . $opt{'fqdn'}))   {
    printmsg($conf{'error'}, 0);
    printmsg("NOTICE => EHLO command failed, attempting HELO instead");
    if (SMTPchat('HELO ' . $opt{'fqdn'})) { quit($conf{'error'}, 1); }
    if ( $opt{'username'} and $opt{'password'} ) {
        printmsg("WARNING => The mail server does not support SMTP authentication!", 0);
    }
}
else {
    
    ## Determin if the server supports TLS
    if ($conf{'SMTPchat_response'} =~ /STARTTLS/) {
        $conf{'tls_server'} = 1;
        printmsg("DEBUG => The remote SMTP server supports TLS :)", 2);
    }
    else {
        $conf{'tls_server'} = 0;
        printmsg("DEBUG => The remote SMTP server does NOT support TLS :(", 2);
    }
    
    ## Start TLS if possible
    if ($conf{'tls_server'} == 1 and $conf{'tls_client'} == 1 and $opt{'tls'} =~ /^(yes|auto)$/) {
        printmsg("DEBUG => Starting TLS", 2);
        if (SMTPchat('STARTTLS')) { quit($conf{'error'}, 1); }
        if (! IO::Socket::SSL->start_SSL($SERVER, SSL_version => 'SSLv3 TLSv1')) {
            quit("ERROR => TLS setup failed: " . IO::Socket::SSL::errstr(), 1);
        }
        printmsg("DEBUG => TLS: Using cipher: ". $SERVER->get_cipher(), 3);
        printmsg("DEBUG => TLS session initialized :)", 1);
        
        ## Restart our SMTP session
        if (SMTPchat('EHLO ' . $opt{'fqdn'})) { quit($conf{'error'}, 1); }
    }
    elsif ($opt{'tls'} eq 'yes' and $conf{'tls_server'} == 0) {
        quit("ERROR => TLS not possible! Remote SMTP server, $conf{'server'},  does not support it.", 1);
    }
    
    
    ## Do SMTP Auth if required
    if ( $opt{'username'} and $opt{'password'} ) {
        if ($conf{'SMTPchat_response'} !~ /AUTH\s/) {
            printmsg("NOTICE => Authentication not supported by the remote SMTP server!", 0);
        }
        else {
            # ## SASL CRAM-MD5 authentication method
            # if ($conf{'SMTPchat_response'} =~ /\bCRAM-MD5\b/i) {
            #     printmsg("DEBUG => SMTP-AUTH: Using CRAM-MD5 authentication method", 1);
            #     if (SMTPchat('AUTH CRAM-MD5')) { quit($conf{'error'}, 1); }
            #     
            #     ## FIXME!!
            #     
            #     printmsg("DEBUG => User authentication was successful", 1);
            # }
            
            ## SASL PLAIN authentication method
            if ($conf{'SMTPchat_response'} =~ /\bPLAIN\b/i) {
                printmsg("DEBUG => SMTP-AUTH: Using PLAIN authentication method", 1);
                if (SMTPchat('AUTH PLAIN ' . base64_encode("$opt{'username'}\0$opt{'username'}\0$opt{'password'}"))) { quit($conf{'error'}, 1); }
                printmsg("DEBUG => User authentication was successful", 1);
            }
            
            ## SASL LOGIN authentication method
            elsif ($conf{'SMTPchat_response'} =~ /\bLOGIN\b/i) {
                printmsg("DEBUG => SMTP-AUTH: Using LOGIN authentication method", 1);
                if (SMTPchat('AUTH LOGIN')) { quit($conf{'error'}, 1); }
                if (SMTPchat(base64_encode($opt{'username'}))) { quit($conf{'error'}, 1); }
                if (SMTPchat(base64_encode($opt{'password'}))) { quit($conf{'error'}, 1); }
                printmsg("DEBUG => User authentication was successful", 1);
            }
            
            else {
                printmsg("WARNING => SMTP-AUTH: No mutually supported authentication methods available", 0);
            }
        }
    }
}

## MAIL FROM
if (SMTPchat('MAIL FROM:<' .(returnAddressParts($from))[1]. '>')) { quit($conf{'error'}, 1); }

## RCPT TO
my $oneRcptAccepted = 0;
foreach my $rcpt (@to, @cc, @bcc) {
    my ($name, $address) = returnAddressParts($rcpt);
    if (SMTPchat('RCPT TO:<' . $address . '>')) {
        printmsg("WARNING => The recipient <$address> was rejected by the mail server, error follows:", 0);
        $conf{'error'} =~ s/^ERROR/WARNING/o;
        printmsg($conf{'error'}, 0);
    }
    elsif ($oneRcptAccepted == 0) {
        $oneRcptAccepted = 1;
    }
}
## If no recipients were accepted we need to exit with an error.
if ($oneRcptAccepted == 0) {
    quit("ERROR => Exiting. No recipients were accepted for delivery by the mail server.", 1);
}

## DATA
if (SMTPchat('DATA')) { quit($conf{'error'}, 1); }


###############################
##  Build and send the body  ##
###############################
printmsg("INFO => Sending message body",1);

## If the message-format is raw just send the message as-is.
if ($opt{'message-format'} =~ /^raw$/i) {
    print $SERVER $message;
}

## If the message-format isn't raw, then build and send the message,
else {
    
    ## Message-ID: <MessageID>
    if ($opt{'message-header'} !~ /^Message-ID:/iom) {
        $header .= 'Message-ID: <' . $conf{'Message-ID'} . '@' . $conf{'hostname'} . '>' . $CRLF;
    }
    
    ## From: "Name" <address@domain.com> (the pointless test below is just to keep scoping correct)
    if ($from and $opt{'message-header'} !~ /^From:/iom) {
        my ($name, $address) = returnAddressParts($from);
        $header .= 'From: "' . $name . '" <' . $address . '>' . $CRLF;
    }
    
    ## Reply-To: 
    if ($opt{'reply-to'} and $opt{'message-header'} !~ /^Reply-To:/iom) {
        my ($name, $address) = returnAddressParts($opt{'reply-to'});
        $header .= 'Reply-To: "' . $name . '" <' . $address . '>' . $CRLF;
    }
    
    ## To: "Name" <address@domain.com>
    if ($opt{'message-header'} =~ /^To:/iom) {
        ## The user put the To: header in via -o message-header - dont do anything
    }
    elsif (scalar(@to) > 0) {
        $header .= "To:";
        for (my $a = 0; $a < scalar(@to); $a++) {
            my $msg = "";
            
            my ($name, $address) = returnAddressParts($to[$a]);
            $msg = " \"$name\" <$address>";
            
            ## If we're not on the last address add a comma to the end of the line.
            if (($a + 1) != scalar(@to)) {
                $msg .= ",";
            }
            
            $header .= $msg . $CRLF;
        }
    }
    ## We always want a To: line so if the only recipients were bcc'd they don't see who it was sent to
    else {
        $header .= "To: \"Undisclosed Recipients\" <>$CRLF";
    }
    
    if (scalar(@cc) > 0 and $opt{'message-header'} !~ /^Cc:/iom) {
        $header .= "Cc:";
        for (my $a = 0; $a < scalar(@cc); $a++) {
            my $msg = "";
            
            my ($name, $address) = returnAddressParts($cc[$a]);
            $msg = " \"$name\" <$address>";
            
            ## If we're not on the last address add a comma to the end of the line.
            if (($a + 1) != scalar(@cc)) {
                $msg .= ",";
            }
            
            $header .= $msg . $CRLF;
        }
    }
    
    if ($opt{'message-header'} !~ /^Subject:/iom) {
        $header .= 'Subject: ' . $subject . $CRLF;                   ## Subject
    }
    if ($opt{'message-header'} !~ /^Date:/iom) {
        $header .= 'Date: ' . $date . $CRLF;                         ## Date
    }
    if ($opt{'message-header'} !~ /^X-Mailer:/iom) {
        $header .= 'X-Mailer: sendEmail-'.$conf{'version'}.$CRLF;    ## X-Mailer
    }
    ## I wonder if I should put this in by default?
    # if ($opt{'message-header'} !~ /^X-Originating-IP:/iom) {
    #     $header .= 'X-Originating-IP: ['.$conf{'ip'}.']'.$CRLF;      ## X-Originating-IP
    # }
    
    ## Encode all messages with MIME.
    if ($opt{'message-header'} !~ /^MIME-Version:/iom) {
        $header .=  "MIME-Version: 1.0$CRLF";
    }
    if ($opt{'message-header'} !~ /^Content-Type:/iom) {
        my $content_type = 'multipart/mixed';
        if (scalar(@attachments) == 0) { $content_type = 'multipart/related'; }
        $header .= "Content-Type: $content_type; boundary=\"$conf{'delimiter'}\"$CRLF";
    }
    
    ## Send additional message header line(s) if specified
    if ($opt{'message-header'}) {
        $header .= $opt{'message-header'};
    }
    
    ## Send the message header to the server
    print $SERVER $header . $CRLF;
    
    ## Start sending the message body to the server
    print $SERVER "This is a multi-part message in MIME format. To properly display this message you need a MIME-Version 1.0 compliant Email program.$CRLF";
    print $SERVER "$CRLF";
    
    
    ## Send message body
    print $SERVER "--$conf{'delimiter'}$CRLF";
    ## If the message contains HTML change the Content-Type
    if ($message =~ /^\s*<html>/i) {
        printmsg("Message is in HTML format", 1);
        print $SERVER "Content-Type: text/html;$CRLF";
    }
    ## Otherwise it's a normal text email
    else {
        print $SERVER "Content-Type: text/plain;$CRLF";
    }
    print $SERVER "        charset=\"" . $opt{'message-charset'} . "\"$CRLF";
    print $SERVER "Content-Transfer-Encoding: 7bit$CRLF";
    print $SERVER $CRLF . $message;
    
    
    
    ## Send Attachemnts
    if (scalar(@attachments) > 0) {
        ## Disable the alarm so people on modems can send big attachments
        alarm(0) if ($^O !~ /win/i);  ## alarm() doesn't work in win32
        
        ## Send the attachments
        foreach my $filename (@attachments) {
            ## This is check 2, we already checked this above, but just in case...
            if ( ! -f $filename ) {
                printmsg("ERROR => The file [$filename] doesn't exist!  Email will be sent, but without that attachment.", 0);
            }
            elsif ( ! -r $filename ) {
                printmsg("ERROR => Couldn't open the file [$filename] for reading: $!   Email will be sent, but without that attachment.", 0);
            }
            else {
                printmsg("DEBUG => Sending the attachment [$filename]", 1);
                send_attachment($filename);
            }
        }
    }
    
    
    ## End the mime encoded message
    print $SERVER "$CRLF--$conf{'delimiter'}--$CRLF";  
}


## Tell the server we are done sending the email
print $SERVER "$CRLF.$CRLF";
if (SMTPchat()) { quit($conf{'error'}, 1); }



####################
#  We are done!!!  #
####################

## Disconnect from the server (don't SMTPchat(), it breaks when using TLS)
print $SERVER "QUIT$CRLF";
close $SERVER;






#######################################
##  Generate exit message/log entry  ##
#######################################

if ($conf{'debug'} or $conf{'logging'}) {
    printmsg("Generating a detailed exit message", 3);
    
    ## Put the message together
    my $output = "Email was sent successfully!  From: <" . (returnAddressParts($from))[1] . "> ";
    
    if (scalar(@to) > 0) {
        $output .= "To: ";
        for ($a = 0; $a < scalar(@to); $a++) {
            $output .= "<" . (returnAddressParts($to[$a]))[1] . "> ";
        }
    }
    if (scalar(@cc) > 0) {
        $output .= "Cc: ";
        for ($a = 0; $a < scalar(@cc); $a++) {
            $output .= "<" . (returnAddressParts($cc[$a]))[1] . "> ";
        }
    }
    if (scalar(@bcc) > 0) {
        $output .= "Bcc: ";
        for ($a = 0; $a < scalar(@bcc); $a++) {
            $output .= "<" . (returnAddressParts($bcc[$a]))[1] . "> ";
        }
    }
    $output .= "Subject: [$subject] " if ($subject);
    if (scalar(@attachments_names) > 0) { 
        $output .= "Attachment(s): ";
        foreach(@attachments_names) {
            $output .= "[$_] ";
        }
    }
    $output .= "Server: [$conf{'server'}:$conf{'port'}]";
    
    
######################
#  Exit the program  #
######################
    
    ## Print / Log the detailed message
    quit($output, 0);
}
else {
    ## Or the standard message
    quit("Email was sent successfully!", 0);
}

