#import <UIKit/UIKit.h>
#import "WhiteRaccoon.h"

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

@interface ViewController : UIViewController <WRRequestDelegate>
@property (strong, nonatomic) UITextField *hostField;
@property (strong, nonatomic) UITextField *userField;
@property (strong, nonatomic) UITextField *passwordField;
@property (strong, nonatomic) UIButton *downloadButton;
@property (strong, nonatomic) UIButton *validateButton;
@property (strong, nonatomic) UIImageView *imageView; // to preview downloaded image
@property (strong, nonatomic) WRRequestDownload *currentDownload;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    self.window = [[UIWindow alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
    self.window.backgroundColor = [UIColor whiteColor];
    ViewController *vc = [[ViewController alloc] init];
    self.window.rootViewController = vc;
    [self.window makeKeyAndVisible];
    return YES;
}

@end

@implementation ViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor whiteColor];

    CGFloat width = self.view.bounds.size.width - 40;

    // Host field
    self.hostField = [[UITextField alloc] initWithFrame:CGRectMake(20, 100, width, 40)];
    self.hostField.placeholder = @"Host (e.g. 192.168.1.10)";
    self.hostField.borderStyle = UITextBorderStyleRoundedRect;
    [self.view addSubview:self.hostField];

    // User field
    self.userField = [[UITextField alloc] initWithFrame:CGRectMake(20, 160, width, 40)];
    self.userField.placeholder = @"User";
    self.userField.borderStyle = UITextBorderStyleRoundedRect;
    [self.view addSubview:self.userField];

    // Password field
    self.passwordField = [[UITextField alloc] initWithFrame:CGRectMake(20, 220, width, 40)];
    self.passwordField.placeholder = @"Password";
    self.passwordField.borderStyle = UITextBorderStyleRoundedRect;
    self.passwordField.secureTextEntry = YES;
    [self.view addSubview:self.passwordField];

    // Download button
    self.downloadButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.downloadButton.frame = CGRectMake(20, 280, width, 44);
    [self.downloadButton setTitle:@"Download" forState:UIControlStateNormal];
    self.downloadButton.backgroundColor = [UIColor systemBlueColor];
    [self.downloadButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    self.downloadButton.layer.cornerRadius = 8;
    [self.downloadButton addTarget:self action:@selector(downloadTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.downloadButton];

    // Validate button
    self.validateButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.validateButton.frame = CGRectMake(20, 340, width, 44);
    [self.validateButton setTitle:@"Validate" forState:UIControlStateNormal];
    self.validateButton.backgroundColor = [UIColor systemGreenColor];
    [self.validateButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    self.validateButton.layer.cornerRadius = 8;
    [self.validateButton addTarget:self action:@selector(validateTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.validateButton];

    // Image preview
    self.imageView = [[UIImageView alloc] initWithFrame:CGRectMake(20, 400, width, 200)];
    self.imageView.contentMode = UIViewContentModeScaleAspectFit;
    self.imageView.backgroundColor = [UIColor colorWithWhite:0.95 alpha:1];
    [self.view addSubview:self.imageView];
}

#pragma mark - Button Actions

- (void)validateTapped {
    NSString *message = [NSString stringWithFormat:@"Host: %@\nUser: %@\nPassword: %@",
                         self.hostField.text,
                         self.userField.text,
                         self.passwordField.text];
    [self showAlertWithTitle:@"Entered Information" message:message];
}

- (void)downloadTapped {
    NSString *host = self.hostField.text;
    NSString *user = self.userField.text;
    NSString *pass = self.passwordField.text;

    if (host.length == 0) {
        [self showAlertWithTitle:@"Error" message:@"Please enter a host."];
        return;
    }

    // Append port 2121 to hostname
    NSString *hostWithPort = [NSString stringWithFormat:@"%@:2121", host];

    // Create download object
    self.currentDownload = [[WRRequestDownload alloc] init];
    self.currentDownload.delegate = self;
    self.currentDownload.hostname = hostWithPort;
    self.currentDownload.username = user.length ? user : nil;
    self.currentDownload.password = pass.length ? pass : nil;
    self.currentDownload.path = @"/download"; // adjust as needed

    // Show fullURL from WRRequest (now includes port) before starting download
    NSURL *url = self.currentDownload.fullURL;
    UIAlertController *urlAlert = [UIAlertController alertControllerWithTitle:@"Full FTP URL"
                                                                      message:url.absoluteString
                                                               preferredStyle:UIAlertControllerStyleAlert];
    UIAlertAction *okAction = [UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:^(UIAlertAction * _Nonnull action) {
        // Start download after user presses OK
        [self.currentDownload start];
        [self showAlertWithTitle:@"Downloading…" message:@"FTP download started."];
    }];
    [urlAlert addAction:okAction];
    [self presentViewController:urlAlert animated:YES completion:nil];
}

#pragma mark - WRRequestDelegate

- (void)requestCompleted:(WRRequest *)request {
    WRRequestDownload *download = (WRRequestDownload *)request;
    NSData *data = download.receivedData;
    UIImage *image = [UIImage imageWithData:data];
    if (image) {
        self.imageView.image = image;
        [self showAlertWithTitle:@"Success" message:@"Image downloaded successfully!"];
    } else {
        [self showAlertWithTitle:@"Download Complete" message:@"File downloaded (non-image or no data)."];
    }
}

- (void)requestFailed:(WRRequest *)request {
    NSString *err = [NSString stringWithFormat:@"Error: %@", request.error.message];
    [self showAlertWithTitle:@"Download Failed" message:err];
}

#pragma mark - Helpers

- (void)showAlertWithTitle:(NSString *)title message:(NSString *)message {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:title
                                                                   message:message
                                                            preferredStyle:UIAlertControllerStyleAlert];
    UIAlertAction *okAction = [UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil];
    [alert addAction:okAction];
    [self presentViewController:alert animated:YES completion:nil];
}

@end

int main(int argc, char * argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
